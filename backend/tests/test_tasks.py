"""Background tasks: stale detection, day rollover and retention."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from locations.models import LocationAnomaly, LocationUpdate
from locations.tasks import purge_expired_location_history
from presence.enums import PresenceEventType, PresenceStatus, TransitionReason
from presence.models import Presence, PresenceEvent
from presence.tasks import (
    close_abandoned_presence_days_task,
    detect_stale_presence,
    purge_expired_presence_events,
)
from tests.conftest import offset_point

pytestmark = pytest.mark.django_db

CENTRE = offset_point()


def check_in(submit, account, *, minutes_ago: int):
    now = timezone.now()
    base = now - timedelta(minutes=minutes_ago)
    for index in range(2):
        submit(
            account,
            latitude=CENTRE[0],
            longitude=CENTRE[1],
            recorded_at=base + timedelta(seconds=60 * index),
        )


class TestStaleDetection:
    def test_a_silent_present_user_becomes_stale_not_gone(
        self, user, circle_geofence, submit_location
    ):
        check_in(submit_location, user, minutes_ago=20)
        presence = Presence.objects.get()
        assert presence.status == PresenceStatus.PRESENT

        result = detect_stale_presence()

        presence.refresh_from_db()
        assert result["transitioned"] == 1
        assert presence.status == PresenceStatus.STALE
        assert presence.stale_since is not None
        # Silence is not departure.
        assert presence.check_out_at is None
        assert not PresenceEvent.objects.filter(
            event_type=PresenceEventType.EXITED
        ).exists()

    def test_a_stale_event_is_recorded_with_its_reason(
        self, user, circle_geofence, submit_location
    ):
        check_in(submit_location, user, minutes_ago=20)
        detect_stale_presence()
        event = PresenceEvent.objects.get(event_type=PresenceEventType.STALE)
        assert event.previous_status == PresenceStatus.PRESENT
        assert event.new_status == PresenceStatus.STALE
        assert event.reason == TransitionReason.UPDATES_TIMED_OUT
        assert event.metadata["timeout_seconds"] == 300

    def test_a_recently_seen_user_is_left_alone(
        self, user, circle_geofence, submit_location
    ):
        check_in(submit_location, user, minutes_ago=1)
        detect_stale_presence()
        assert Presence.objects.get().status == PresenceStatus.PRESENT

    def test_the_sweep_is_idempotent(self, user, circle_geofence, submit_location):
        check_in(submit_location, user, minutes_ago=20)
        detect_stale_presence()
        second = detect_stale_presence()
        assert second["transitioned"] == 0
        assert PresenceEvent.objects.filter(event_type=PresenceEventType.STALE).count() == 1

    def test_non_present_rows_are_never_touched(
        self, user, organization, circle_geofence
    ):
        for status in (PresenceStatus.UNKNOWN, PresenceStatus.OUTSIDE, PresenceStatus.GONE):
            Presence.objects.update_or_create(
                user=user,
                geofence=circle_geofence,
                date=timezone.now().date(),
                defaults={
                    "organization": organization,
                    "status": status,
                    "last_seen_at": timezone.now() - timedelta(hours=2),
                },
            )
            detect_stale_presence()
            assert Presence.objects.get().status == status

    def test_a_geofence_can_override_the_timeout(
        self, user, circle_geofence, submit_location
    ):
        circle_geofence.stale_after_seconds = 7200
        circle_geofence.save(update_fields=["stale_after_seconds"])

        check_in(submit_location, user, minutes_ago=20)
        detect_stale_presence()
        assert Presence.objects.get().status == PresenceStatus.PRESENT

    def test_updates_resume_and_restore_presence(
        self, user, circle_geofence, submit_location
    ):
        check_in(submit_location, user, minutes_ago=20)
        detect_stale_presence()
        assert Presence.objects.get().status == PresenceStatus.STALE

        submit_location(user, latitude=CENTRE[0], longitude=CENTRE[1])

        presence = Presence.objects.get()
        assert presence.status == PresenceStatus.PRESENT
        assert presence.stale_since is None
        assert PresenceEvent.objects.filter(
            event_type=PresenceEventType.LOCATION_RESTORED
        ).exists()

    def test_the_task_is_wired_into_celery(self, user, circle_geofence, submit_location):
        check_in(submit_location, user, minutes_ago=20)
        # CELERY_TASK_ALWAYS_EAGER is enabled in the test settings.
        result = detect_stale_presence.delay()
        assert result.get()["transitioned"] == 1


class TestDayRollover:
    def test_a_day_that_ended_while_checked_in_is_closed(
        self, user, organization, circle_geofence
    ):
        yesterday = timezone.now().date() - timedelta(days=1)
        last_seen = timezone.now() - timedelta(days=1)
        Presence.objects.create(
            user=user,
            organization=organization,
            geofence=circle_geofence,
            date=yesterday,
            status=PresenceStatus.PRESENT,
            check_in_at=last_seen - timedelta(hours=3),
            last_seen_at=last_seen,
        )

        close_abandoned_presence_days_task()

        presence = Presence.objects.get()
        assert presence.status == PresenceStatus.GONE
        assert presence.check_out_at == last_seen
        event = PresenceEvent.objects.get(event_type=PresenceEventType.EXITED)
        assert event.reason == TransitionReason.DAY_ROLLOVER

    def test_todays_rows_are_untouched(self, user, circle_geofence, submit_location):
        check_in(submit_location, user, minutes_ago=2)
        close_abandoned_presence_days_task()
        assert Presence.objects.get().status == PresenceStatus.PRESENT


class TestRetention:
    def test_old_location_history_is_purged(
        self, user, organization, circle_geofence, submit_location
    ):
        submit_location(user, latitude=CENTRE[0], longitude=CENTRE[1])
        update = LocationUpdate.objects.get()
        LocationUpdate.objects.filter(pk=update.pk).update(
            received_at=timezone.now() - timedelta(days=90)
        )

        purge_expired_location_history()
        assert not LocationUpdate.objects.exists()

    def test_recent_location_history_is_kept(
        self, user, circle_geofence, submit_location
    ):
        submit_location(user, latitude=CENTRE[0], longitude=CENTRE[1])
        purge_expired_location_history()
        assert LocationUpdate.objects.count() == 1

    def test_old_presence_events_are_purged(
        self, user, organization, circle_geofence, submit_location
    ):
        check_in(submit_location, user, minutes_ago=5)
        PresenceEvent.objects.update(timestamp=timezone.now() - timedelta(days=800))

        purge_expired_presence_events()
        assert not PresenceEvent.objects.exists()

    def test_anomalies_expire_before_presence_history(
        self, user, circle_geofence, submit_location
    ):
        submit_location(
            user, latitude=CENTRE[0], longitude=CENTRE[1], accuracy=900
        )
        assert LocationAnomaly.objects.exists()
        LocationAnomaly.objects.update(created_at=timezone.now() - timedelta(days=120))

        purge_expired_location_history()
        assert not LocationAnomaly.objects.exists()
