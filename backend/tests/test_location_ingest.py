"""End-to-end ingest behaviour: transitions, jitter, delay, duplicates, anomalies.

These drive the service layer directly (no HTTP) so that each test states a
sequence of GPS fixes and asserts the resulting presence, which is exactly how
the feature is specified.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from geofences.enums import ContainmentVerdict
from locations.enums import AnomalySeverity, AnomalyType
from locations.models import LocationAnomaly, LocationUpdate
from presence.enums import PresenceEventType, PresenceStatus
from presence.models import Presence, PresenceEvent
from tests.conftest import offset_point

pytestmark = pytest.mark.django_db

INSIDE = offset_point(metres_north=0)  # centre of the circle
NEAR_EDGE = offset_point(metres_north=170)  # in the hysteresis band
OUTSIDE = offset_point(metres_north=400)  # well beyond the exit radius


def feed(submit, user, positions, *, start_offset_minutes=10, accuracy=10.0, spacing=60):
    """Submit a sequence of fixes ending near now, one per ``spacing`` seconds."""
    now = timezone.now()
    base = now - timedelta(minutes=start_offset_minutes)
    results = []
    for index, (latitude, longitude) in enumerate(positions):
        results.append(
            submit(
                user,
                latitude=latitude,
                longitude=longitude,
                accuracy=accuracy,
                recorded_at=base + timedelta(seconds=spacing * index),
            )
        )
    return results


def presence_of(user, geofence) -> Presence | None:
    return Presence.objects.filter(user=user, geofence=geofence).first()


class TestEntryTransition:
    def test_first_inside_reading_does_not_check_in(
        self, user, circle_geofence, submit_location
    ):
        feed(submit_location, user, [INSIDE])
        presence = presence_of(user, circle_geofence)
        assert presence is not None
        assert presence.status == PresenceStatus.UNKNOWN
        assert presence.consecutive_inside == 1
        assert presence.check_in_at is None
        assert not PresenceEvent.objects.exists()

    def test_two_inside_readings_check_in(self, user, circle_geofence, submit_location):
        feed(submit_location, user, [INSIDE, INSIDE])
        presence = presence_of(user, circle_geofence)
        assert presence.status == PresenceStatus.PRESENT
        assert presence.check_in_at is not None
        assert presence.last_verdict == ContainmentVerdict.INSIDE
        events = list(PresenceEvent.objects.values_list("event_type", flat=True))
        assert events == [PresenceEventType.ENTERED]

    def test_check_in_uses_device_time_not_server_time(
        self, user, circle_geofence, submit_location
    ):
        results = feed(submit_location, user, [INSIDE, INSIDE])
        presence = presence_of(user, circle_geofence)
        assert presence.check_in_at == results[-1].location_update.recorded_at
        assert presence.check_in_at != results[-1].location_update.received_at

    def test_repeated_readings_do_not_duplicate_the_event(
        self, user, circle_geofence, submit_location
    ):
        feed(submit_location, user, [INSIDE] * 8)
        assert (
            PresenceEvent.objects.filter(event_type=PresenceEventType.ENTERED).count() == 1
        )

    def test_no_presence_row_for_a_user_who_is_only_ever_outside(
        self, user, circle_geofence, submit_location
    ):
        feed(submit_location, user, [OUTSIDE] * 5)
        # Lazy creation: never inside, so nothing to track.
        assert not Presence.objects.exists()
        assert LocationUpdate.objects.count() == 5


class TestExitTransition:
    def test_three_outside_readings_check_out(
        self, user, circle_geofence, submit_location
    ):
        feed(submit_location, user, [INSIDE, INSIDE, OUTSIDE, OUTSIDE, OUTSIDE])
        presence = presence_of(user, circle_geofence)
        assert presence.status == PresenceStatus.GONE
        assert presence.check_out_at is not None
        assert list(
            PresenceEvent.objects.order_by("timestamp").values_list("event_type", flat=True)
        ) == [PresenceEventType.ENTERED, PresenceEventType.EXITED]

    def test_two_outside_readings_are_not_enough(
        self, user, circle_geofence, submit_location
    ):
        feed(submit_location, user, [INSIDE, INSIDE, OUTSIDE, OUTSIDE])
        assert presence_of(user, circle_geofence).status == PresenceStatus.PRESENT

    def test_re_entry_reopens_presence_without_losing_the_first_check_in(
        self, user, circle_geofence, submit_location
    ):
        feed(
            submit_location,
            user,
            [INSIDE, INSIDE, OUTSIDE, OUTSIDE, OUTSIDE, INSIDE, INSIDE],
        )
        presence = presence_of(user, circle_geofence)
        assert presence.status == PresenceStatus.PRESENT
        first_entered = (
            PresenceEvent.objects.filter(event_type=PresenceEventType.ENTERED)
            .order_by("timestamp")
            .first()
        )
        assert presence.check_in_at == first_entered.timestamp
        assert (
            PresenceEvent.objects.filter(event_type=PresenceEventType.ENTERED).count() == 2
        )


class TestJitterAndAccuracy:
    def test_boundary_jitter_does_not_flip_the_state(
        self, user, circle_geofence, submit_location
    ):
        feed(
            submit_location,
            user,
            [INSIDE, INSIDE, NEAR_EDGE, NEAR_EDGE, NEAR_EDGE, NEAR_EDGE],
        )
        presence = presence_of(user, circle_geofence)
        assert presence.status == PresenceStatus.PRESENT
        assert presence.last_verdict == ContainmentVerdict.UNCERTAIN

    def test_one_outside_blip_between_inside_readings_is_absorbed(
        self, user, circle_geofence, submit_location
    ):
        feed(
            submit_location,
            user,
            [INSIDE, INSIDE, OUTSIDE, OUTSIDE, INSIDE, OUTSIDE, OUTSIDE],
        )
        assert presence_of(user, circle_geofence).status == PresenceStatus.PRESENT

    def test_poor_accuracy_cannot_check_a_user_in(
        self, user, circle_geofence, submit_location
    ):
        position = offset_point(metres_north=60)
        feed(submit_location, user, [position] * 3, accuracy=500)
        # 60 m from the centre but with a 150 m (capped) uncertainty margin:
        # the fix cannot prove containment either way.
        assert not Presence.objects.filter(status=PresenceStatus.PRESENT).exists()

    def test_poor_accuracy_is_flagged_but_still_stored(
        self, user, circle_geofence, submit_location
    ):
        feed(submit_location, user, [INSIDE], accuracy=500)
        update = LocationUpdate.objects.get()
        assert update.is_flagged is True
        assert update.is_trusted is True  # not blocking, just low confidence
        assert update.confidence == "LOW"
        assert LocationAnomaly.objects.filter(
            anomaly_type=AnomalyType.POOR_ACCURACY
        ).exists()

    def test_good_accuracy_near_the_edge_still_checks_in(
        self, user, circle_geofence, submit_location
    ):
        position = offset_point(metres_north=120)
        feed(submit_location, user, [position] * 2, accuracy=10)
        assert presence_of(user, circle_geofence).status == PresenceStatus.PRESENT

    def test_streak_resets_after_a_long_silence(
        self, user, circle_geofence, submit_location
    ):
        now = timezone.now()
        submit_location(
            user, latitude=INSIDE[0], longitude=INSIDE[1], recorded_at=now - timedelta(minutes=50)
        )
        submit_location(user, latitude=INSIDE[0], longitude=INSIDE[1], recorded_at=now)
        # 50 minutes apart is not a streak (STREAK_MAX_GAP_SECONDS = 300).
        presence = presence_of(user, circle_geofence)
        assert presence.status == PresenceStatus.UNKNOWN
        assert presence.consecutive_inside == 1


class TestDelayAndOrdering:
    def test_delayed_fix_is_accepted_and_uses_its_own_timestamp(
        self, user, circle_geofence, submit_location
    ):
        recorded = timezone.now() - timedelta(minutes=15)
        result = submit_location(
            user, latitude=INSIDE[0], longitude=INSIDE[1], recorded_at=recorded
        )
        update = result.location_update
        assert update.recorded_at == recorded
        assert update.received_at > recorded
        assert update.delay_seconds > 800

    def test_out_of_order_fix_does_not_rewind_the_state(
        self, user, circle_geofence, submit_location
    ):
        now = timezone.now()
        for index in range(2):
            submit_location(
                user,
                latitude=INSIDE[0],
                longitude=INSIDE[1],
                recorded_at=now - timedelta(seconds=120 - 60 * index),
            )
        presence = presence_of(user, circle_geofence)
        assert presence.status == PresenceStatus.PRESENT
        last_seen = presence.last_seen_at

        # A straggler from before the check-in arrives late.
        result = submit_location(
            user,
            latitude=OUTSIDE[0],
            longitude=OUTSIDE[1],
            recorded_at=now - timedelta(seconds=300),
        )
        presence.refresh_from_db()
        assert presence.status == PresenceStatus.PRESENT
        assert presence.last_seen_at == last_seen
        assert result.outcomes[0].skip_reason == "OUT_OF_ORDER"

    def test_a_fix_older_than_the_limit_is_rejected(self, user, circle_geofence):
        from common.exceptions import ValidationFailed
        from locations.validators import validate_recorded_at

        with pytest.raises(ValidationFailed):
            validate_recorded_at(timezone.now() - timedelta(hours=5))

    def test_a_fix_from_the_future_is_rejected(self, user):
        from common.exceptions import ValidationFailed
        from locations.validators import validate_recorded_at

        with pytest.raises(ValidationFailed):
            validate_recorded_at(timezone.now() + timedelta(minutes=30))

    def test_small_clock_skew_is_tolerated_but_flagged(
        self, user, circle_geofence, submit_location
    ):
        result = submit_location(
            user,
            latitude=INSIDE[0],
            longitude=INSIDE[1],
            recorded_at=timezone.now() + timedelta(seconds=30),
        )
        assert result.location_update.pk is not None
        assert LocationAnomaly.objects.filter(
            anomaly_type=AnomalyType.FUTURE_TIMESTAMP
        ).exists()


class TestIdempotency:
    def test_same_client_event_id_is_not_stored_twice(
        self, user, circle_geofence, submit_location
    ):
        recorded = timezone.now() - timedelta(seconds=30)
        first = submit_location(
            user,
            latitude=INSIDE[0],
            longitude=INSIDE[1],
            recorded_at=recorded,
            client_event_id="retry-me",
        )
        second = submit_location(
            user,
            latitude=INSIDE[0],
            longitude=INSIDE[1],
            recorded_at=recorded,
            client_event_id="retry-me",
        )
        assert first.duplicate is False
        assert second.duplicate is True
        assert second.location_update.pk == first.location_update.pk
        assert LocationUpdate.objects.count() == 1

    def test_a_replay_does_not_advance_the_streak(
        self, user, circle_geofence, submit_location
    ):
        recorded = timezone.now() - timedelta(seconds=30)
        for _ in range(4):
            submit_location(
                user,
                latitude=INSIDE[0],
                longitude=INSIDE[1],
                recorded_at=recorded,
                client_event_id="same-key",
            )
        presence = presence_of(user, circle_geofence)
        assert presence.consecutive_inside == 1
        assert presence.status == PresenceStatus.UNKNOWN

    def test_identical_timestamp_without_a_key_is_treated_as_a_replay(
        self, user, circle_geofence, submit_location
    ):
        recorded = timezone.now() - timedelta(seconds=30)
        submit_location(user, latitude=INSIDE[0], longitude=INSIDE[1], recorded_at=recorded)
        second = submit_location(
            user, latitude=INSIDE[0], longitude=INSIDE[1], recorded_at=recorded
        )
        assert second.duplicate is True
        assert LocationUpdate.objects.count() == 1

    def test_different_users_may_reuse_the_same_client_event_id(
        self, user, other_user, circle_geofence, submit_location
    ):
        recorded = timezone.now() - timedelta(seconds=30)
        for account in (user, other_user):
            submit_location(
                account,
                latitude=INSIDE[0],
                longitude=INSIDE[1],
                recorded_at=recorded,
                client_event_id="shared-key",
            )
        assert LocationUpdate.objects.count() == 2


class TestAnomalies:
    def test_impossible_speed_is_flagged_and_excluded(
        self, user, circle_geofence, submit_location
    ):
        now = timezone.now()
        submit_location(
            user,
            latitude=INSIDE[0],
            longitude=INSIDE[1],
            recorded_at=now - timedelta(seconds=60),
        )
        result = submit_location(
            user,
            latitude=INSIDE[0] + 1.0,  # ~111 km north
            longitude=INSIDE[1],
            recorded_at=now,
        )
        assert result.trusted is False
        assert result.skipped_reason == "UNTRUSTED_READING"
        assert LocationAnomaly.objects.filter(
            anomaly_type=AnomalyType.IMPOSSIBLE_SPEED, severity=AnomalySeverity.HIGH
        ).exists()
        # Stored for the audit trail, but it changed nothing.
        assert LocationUpdate.objects.count() == 2
        assert result.outcomes == []

    def test_an_untrusted_reading_does_not_end_presence(
        self, user, circle_geofence, submit_location
    ):
        now = timezone.now()
        for index in range(2):
            submit_location(
                user,
                latitude=INSIDE[0],
                longitude=INSIDE[1],
                recorded_at=now - timedelta(seconds=180 - 60 * index),
            )
        assert presence_of(user, circle_geofence).status == PresenceStatus.PRESENT

        submit_location(
            user, latitude=INSIDE[0] + 1.0, longitude=INSIDE[1], recorded_at=now
        )
        assert presence_of(user, circle_geofence).status == PresenceStatus.PRESENT

    def test_gps_jitter_is_not_reported_as_impossible_speed(
        self, user, circle_geofence, submit_location
    ):
        """30 m of noise one second apart must not read as 108 km/h."""
        now = timezone.now()
        submit_location(
            user,
            latitude=INSIDE[0],
            longitude=INSIDE[1],
            accuracy=30,
            recorded_at=now - timedelta(seconds=1),
        )
        submit_location(
            user,
            latitude=offset_point(metres_north=30)[0],
            longitude=INSIDE[1],
            accuracy=30,
            recorded_at=now,
        )
        assert not LocationAnomaly.objects.filter(
            anomaly_type=AnomalyType.IMPOSSIBLE_SPEED
        ).exists()

    def test_a_single_anomaly_never_deactivates_a_user(
        self, user, circle_geofence, submit_location
    ):
        now = timezone.now()
        submit_location(
            user,
            latitude=INSIDE[0],
            longitude=INSIDE[1],
            recorded_at=now - timedelta(seconds=60),
        )
        submit_location(
            user, latitude=INSIDE[0] + 1.0, longitude=INSIDE[1], recorded_at=now
        )
        user.refresh_from_db()
        assert user.is_active is True


class TestMultipleGeofences:
    def test_presence_is_tracked_per_geofence(
        self, user, circle_geofence, rectangle_geofence, submit_location
    ):
        feed(submit_location, user, [INSIDE, INSIDE])
        statuses = {
            row.geofence_id: row.status for row in Presence.objects.filter(user=user)
        }
        assert statuses[circle_geofence.pk] == PresenceStatus.PRESENT
        assert statuses[rectangle_geofence.pk] == PresenceStatus.PRESENT

    def test_leaving_the_site_checks_the_user_out_of_every_area(
        self, user, circle_geofence, rectangle_geofence, submit_location
    ):
        # 1 km north clears both the 190 m circle exit radius and the rectangle's
        # 40 m outset, so the user is checked out of both areas.
        feed(submit_location, user, [INSIDE, INSIDE])
        far = offset_point(metres_north=1000)
        feed(submit_location, user, [far] * 3, start_offset_minutes=5)
        statuses = {
            row.geofence_id: row.status for row in Presence.objects.filter(user=user)
        }
        assert statuses[circle_geofence.pk] == PresenceStatus.GONE
        assert statuses[rectangle_geofence.pk] == PresenceStatus.GONE
