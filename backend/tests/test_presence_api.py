"""Self-service and administrative presence endpoints."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from presence.enums import PresenceEventType, PresenceStatus
from presence.models import Presence
from tests.conftest import offset_point
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

CENTRE = offset_point()
FAR = offset_point(metres_north=1000)


def check_in(submit, account, *, minutes_ago: int = 5):
    now = timezone.now()
    for index in range(2):
        submit(
            account,
            latitude=CENTRE[0],
            longitude=CENTRE[1],
            recorded_at=now - timedelta(minutes=minutes_ago) + timedelta(seconds=60 * index),
        )


class TestMyPresence:
    def test_unknown_when_nothing_was_reported(self, user_client, circle_geofence):
        response = user_client.get(reverse("presence:presence-me"))
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["effective_status"] == PresenceStatus.UNKNOWN
        assert data["geofences"] == []

    def test_reports_present_after_check_in(
        self, user_client, user, circle_geofence, submit_location
    ):
        check_in(submit_location, user)
        data = user_client.get(reverse("presence:presence-me")).json()["data"]
        assert data["effective_status"] == PresenceStatus.PRESENT
        row = data["geofences"][0]
        assert row["geofence_name"] == circle_geofence.name
        assert row["check_in_at"] is not None
        assert row["current_location"]["accuracy"] == 10.0

    def test_history_lists_previous_days(
        self, user_client, user, organization, circle_geofence, submit_location
    ):
        check_in(submit_location, user)
        Presence.objects.create(
            user=user,
            organization=organization,
            geofence=circle_geofence,
            date=timezone.now().date() - timedelta(days=3),
            status=PresenceStatus.GONE,
        )
        response = user_client.get(reverse("presence:presence-me-history"))
        assert response.json()["data"]["count"] == 2

    def test_history_can_be_filtered_by_date_range(
        self, user_client, user, organization, circle_geofence
    ):
        today = timezone.now().date()
        for offset in range(4):
            Presence.objects.create(
                user=user,
                organization=organization,
                geofence=circle_geofence,
                date=today - timedelta(days=offset),
                status=PresenceStatus.GONE,
            )
        response = user_client.get(
            reverse("presence:presence-me-history"),
            {"date_from": (today - timedelta(days=1)).isoformat()},
        )
        assert response.json()["data"]["count"] == 2

    def test_a_user_never_sees_another_users_presence(
        self, as_user, user, other_user, circle_geofence, submit_location
    ):
        check_in(submit_location, other_user)
        data = as_user(user).get(reverse("presence:presence-me")).json()["data"]
        assert data["geofences"] == []

    def test_own_events_are_visible(
        self, user_client, user, circle_geofence, submit_location
    ):
        check_in(submit_location, user)
        response = user_client.get(reverse("presence:presence-me-events"))
        types = [row["event_type"] for row in response.json()["data"]["results"]]
        assert types == [PresenceEventType.ENTERED]


class TestAdminPresenceList:
    def test_members_are_refused(self, user_client):
        assert user_client.get(reverse("presence:admin-presence")).status_code == 403

    def test_admin_sees_todays_rows_by_default(
        self, admin_client, user, circle_geofence, submit_location
    ):
        check_in(submit_location, user)
        response = admin_client.get(reverse("presence:admin-presence"))
        assert response.status_code == 200
        rows = response.json()["data"]["results"]
        assert len(rows) == 1
        assert rows[0]["user_id"] == user.pk
        assert rows[0]["status"] == PresenceStatus.PRESENT
        assert rows[0]["current_location"]["latitude"] == pytest.approx(CENTRE[0])

    def test_filter_by_status(
        self, admin_client, user, other_user, circle_geofence, submit_location
    ):
        check_in(submit_location, user)
        response = admin_client.get(
            reverse("presence:admin-presence"), {"status": PresenceStatus.PRESENT}
        )
        assert response.json()["data"]["count"] == 1
        response = admin_client.get(
            reverse("presence:admin-presence"), {"status": PresenceStatus.GONE}
        )
        assert response.json()["data"]["count"] == 0

    def test_filter_by_user_and_geofence(
        self, admin_client, user, circle_geofence, submit_location
    ):
        check_in(submit_location, user)
        response = admin_client.get(
            reverse("presence:admin-presence"),
            {"user": user.pk, "geofence": circle_geofence.pk},
        )
        assert response.json()["data"]["count"] == 1

    def test_results_are_paginated(self, admin_client, organization, circle_geofence):
        today = timezone.now().date()
        for index in range(30):
            member = UserFactory(organization=organization)
            Presence.objects.create(
                user=member,
                organization=organization,
                geofence=circle_geofence,
                date=today,
                status=PresenceStatus.PRESENT,
            )
        body = admin_client.get(reverse("presence:admin-presence")).json()["data"]
        assert body["count"] == 30
        assert len(body["results"]) == 25
        assert body["next"] is not None

    def test_never_leaks_another_organization(
        self, as_user, foreign_admin, user, circle_geofence, submit_location
    ):
        check_in(submit_location, user)
        response = as_user(foreign_admin).get(reverse("presence:admin-presence"))
        assert response.json()["data"]["count"] == 0


class TestAdminUserDetail:
    def test_returns_rows_and_events(
        self, admin_client, user, circle_geofence, submit_location
    ):
        check_in(submit_location, user)
        response = admin_client.get(
            reverse("presence:admin-presence-user", args=[user.pk])
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["effective_status"] == PresenceStatus.PRESENT
        assert len(data["today"]) == 1
        assert data["events"][0]["event_type"] == PresenceEventType.ENTERED

    def test_a_foreign_user_is_not_found(
        self, as_user, foreign_admin, user, circle_geofence, submit_location
    ):
        check_in(submit_location, user)
        response = as_user(foreign_admin).get(
            reverse("presence:admin-presence-user", args=[user.pk])
        )
        assert response.status_code == 404


class TestAdminSummary:
    def test_counts_every_state(
        self, admin_client, organization, user, circle_geofence, submit_location
    ):
        check_in(submit_location, user)
        # Two more members who never reported anything.
        UserFactory(organization=organization)
        UserFactory(organization=organization)

        data = admin_client.get(reverse("presence:admin-presence-summary")).json()["data"]
        assert data["present"] == 1
        assert data["unknown"] >= 2
        assert data["total_users"] == data["present"] + data["unknown"] + data["gone"] + data[
            "outside"
        ] + data["stale"]

    def test_includes_per_geofence_occupancy(
        self, admin_client, user, circle_geofence, submit_location
    ):
        check_in(submit_location, user)
        data = admin_client.get(reverse("presence:admin-presence-summary")).json()["data"]
        assert data["by_geofence"][0]["geofence_id"] == circle_geofence.pk
        assert data["by_geofence"][0]["present"] == 1

    def test_missing_gps_counts_as_unknown_never_as_gone(
        self, admin_client, organization, circle_geofence
    ):
        UserFactory(organization=organization)
        data = admin_client.get(reverse("presence:admin-presence-summary")).json()["data"]
        assert data["gone"] == 0
        assert data["unknown"] == data["total_users"]


class TestAdminEvents:
    def test_events_are_listed_newest_first(
        self, admin_client, user, circle_geofence, submit_location
    ):
        check_in(submit_location, user)
        now = timezone.now()
        for index in range(3):
            submit_location(
                user,
                latitude=FAR[0],
                longitude=FAR[1],
                recorded_at=now - timedelta(seconds=120 - 60 * index),
            )
        results = admin_client.get(reverse("presence:admin-presence-events")).json()["data"][
            "results"
        ]
        assert [row["event_type"] for row in results] == [
            PresenceEventType.EXITED,
            PresenceEventType.ENTERED,
        ]

    def test_events_can_be_filtered_by_type(
        self, admin_client, user, circle_geofence, submit_location
    ):
        check_in(submit_location, user)
        response = admin_client.get(
            reverse("presence:admin-presence-events"),
            {"event_type": PresenceEventType.EXITED},
        )
        assert response.json()["data"]["count"] == 0

    def test_foreign_admins_see_nothing(
        self, as_user, foreign_admin, user, circle_geofence, submit_location
    ):
        check_in(submit_location, user)
        response = as_user(foreign_admin).get(reverse("presence:admin-presence-events"))
        assert response.json()["data"]["count"] == 0
