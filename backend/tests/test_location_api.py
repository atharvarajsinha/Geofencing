"""HTTP contract of the location endpoints."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from locations.models import LocationUpdate
from presence.enums import PresenceStatus

pytestmark = pytest.mark.django_db

UPDATE_URL = "locations:location-update"
STATUS_URL = "locations:location-status"


def payload(latitude, longitude, *, accuracy=12, recorded_at=None, **extra):
    return {
        "latitude": latitude,
        "longitude": longitude,
        "accuracy": accuracy,
        "recorded_at": (recorded_at or timezone.now()).isoformat(),
        **extra,
    }


class TestLocationUpdateEndpoint:
    def test_authentication_is_required(self, api_client, campus_centre):
        response = api_client.post(reverse(UPDATE_URL), payload(*campus_centre), format="json")
        assert response.status_code == 401

    def test_accepted_fix_returns_the_authoritative_state(
        self, user_client, circle_geofence, campus_centre
    ):
        response = user_client.post(
            reverse(UPDATE_URL), payload(*campus_centre), format="json"
        )
        assert response.status_code == 201, response.json()
        data = response.json()["data"]
        assert data["effective_status"] == PresenceStatus.UNKNOWN  # one reading only
        assert data["presence"][0]["verdict"] == "INSIDE"
        assert data["presence"][0]["consecutive_inside"] == 1
        assert data["next_ping_seconds"] > 0

    def test_two_fixes_check_the_user_in(
        self, user_client, circle_geofence, campus_centre
    ):
        now = timezone.now()
        for index in range(2):
            response = user_client.post(
                reverse(UPDATE_URL),
                payload(*campus_centre, recorded_at=now - timedelta(seconds=60 - 60 * index)),
                format="json",
            )
        assert response.json()["data"]["effective_status"] == PresenceStatus.PRESENT
        assert response.json()["data"]["presence"][0]["events"] == ["ENTERED"]

    def test_client_supplied_status_is_refused(
        self, user_client, circle_geofence, campus_centre
    ):
        response = user_client.post(
            reverse(UPDATE_URL),
            payload(*campus_centre, status="PRESENT"),
            format="json",
        )
        assert response.status_code == 400
        assert "status" in response.json()["errors"]
        assert not LocationUpdate.objects.exists()

    @pytest.mark.parametrize(
        "latitude,longitude",
        [(200, 79.6), (-91, 79.6), (29.5, 181), (29.5, -181)],
    )
    def test_out_of_range_coordinates_are_refused(
        self, user_client, circle_geofence, latitude, longitude
    ):
        response = user_client.post(
            reverse(UPDATE_URL), payload(latitude, longitude), format="json"
        )
        assert response.status_code == 400

    def test_negative_accuracy_is_refused(self, user_client, campus_centre):
        response = user_client.post(
            reverse(UPDATE_URL), payload(*campus_centre, accuracy=-5), format="json"
        )
        assert response.status_code == 400
        assert "accuracy" in response.json()["errors"]

    def test_naive_timestamp_is_refused(self, user_client, campus_centre):
        body = payload(*campus_centre)
        body["recorded_at"] = "2026-08-26T12:20:15"
        response = user_client.post(reverse(UPDATE_URL), body, format="json")
        assert response.status_code == 400
        assert "recorded_at" in response.json()["errors"]

    def test_far_future_timestamp_is_refused(self, user_client, campus_centre):
        response = user_client.post(
            reverse(UPDATE_URL),
            payload(*campus_centre, recorded_at=timezone.now() + timedelta(hours=1)),
            format="json",
        )
        assert response.status_code == 400
        assert "recorded_at" in response.json()["errors"]

    def test_very_old_fix_is_refused(self, user_client, campus_centre):
        response = user_client.post(
            reverse(UPDATE_URL),
            payload(*campus_centre, recorded_at=timezone.now() - timedelta(hours=6)),
            format="json",
        )
        assert response.status_code == 400

    def test_retry_with_the_same_key_returns_200_and_no_duplicate(
        self, user_client, circle_geofence, campus_centre
    ):
        body = payload(*campus_centre, client_event_id="abc-123")
        first = user_client.post(reverse(UPDATE_URL), body, format="json")
        second = user_client.post(reverse(UPDATE_URL), body, format="json")

        assert first.status_code == 201
        assert second.status_code == 200
        assert second.json()["data"]["duplicate"] is True
        assert LocationUpdate.objects.count() == 1

    def test_user_without_an_organization_is_rejected(self, as_user, platform_admin, campus_centre):
        client = as_user(platform_admin)
        response = client.post(reverse(UPDATE_URL), payload(*campus_centre), format="json")
        assert response.status_code == 400

    def test_response_is_enveloped(self, user_client, circle_geofence, campus_centre):
        response = user_client.post(
            reverse(UPDATE_URL), payload(*campus_centre), format="json"
        )
        body = response.json()
        assert set(body) == {"success", "data"}
        assert body["success"] is True


class TestLocationStatusEndpoint:
    def test_reports_unknown_before_any_fix(self, user_client, circle_geofence):
        response = user_client.get(reverse(STATUS_URL))
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["effective_status"] == PresenceStatus.UNKNOWN
        assert data["last_location"] is None

    def test_reports_the_last_fix_and_the_client_configuration(
        self, user_client, circle_geofence, campus_centre
    ):
        user_client.post(reverse(UPDATE_URL), payload(*campus_centre), format="json")
        data = user_client.get(reverse(STATUS_URL)).json()["data"]
        assert data["last_location"]["accuracy"] == 12
        assert data["client_config"]["max_acceptable_accuracy_m"] == 50.0
        assert data["client_config"]["recommended_ping_interval_seconds"] > 0


class TestHistoryEndpoint:
    def test_a_user_only_ever_sees_their_own_history(
        self, as_user, user, other_user, circle_geofence, campus_centre
    ):
        for account in (user, other_user):
            as_user(account).post(
                reverse(UPDATE_URL), payload(*campus_centre), format="json"
            )

        response = as_user(user).get(reverse("locations:location-history"))
        results = response.json()["data"]["results"]
        assert len(results) == 1
        assert results[0]["user"] == user.pk


class TestAnomalyFeed:
    def test_members_cannot_read_the_anomaly_feed(self, user_client):
        assert user_client.get(reverse("locations:location-anomalies")).status_code == 403

    def test_admins_see_their_organizations_anomalies(
        self, as_user, admin_user, user, circle_geofence, campus_centre
    ):
        # A fix with unusable accuracy produces a POOR_ACCURACY anomaly.
        as_user(user).post(
            reverse(UPDATE_URL), payload(*campus_centre, accuracy=800), format="json"
        )
        response = as_user(admin_user).get(reverse("locations:location-anomalies"))
        assert response.status_code == 200
        results = response.json()["data"]["results"]
        assert [row["anomaly_type"] for row in results] == ["POOR_ACCURACY"]

    def test_a_foreign_admin_sees_nothing(
        self, as_user, foreign_admin, user, circle_geofence, campus_centre
    ):
        as_user(user).post(
            reverse(UPDATE_URL), payload(*campus_centre, accuracy=800), format="json"
        )
        response = as_user(foreign_admin).get(reverse("locations:location-anomalies"))
        assert response.json()["data"]["count"] == 0
