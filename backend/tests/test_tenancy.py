"""Organization isolation.

Every endpoint that can return more than one row is checked against a second
organization, because tenancy leaks are the failure mode with the worst
consequences in this system.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from geofences.evaluation import evaluate_point
from presence.models import Presence
from tests.conftest import offset_point
from tests.factories import CircleGeofenceFactory, UserFactory

pytestmark = pytest.mark.django_db

CENTRE = offset_point()


@pytest.fixture
def foreign_user(other_organization):
    return UserFactory(organization=other_organization, email="foreigner@example.com")


@pytest.fixture
def foreign_geofence(other_organization):
    return CircleGeofenceFactory(organization=other_organization, name="Their Campus")


class TestQuerysetScoping:
    def test_geofence_list_is_scoped(self, user_client, circle_geofence, foreign_geofence):
        response = user_client.get(reverse("geofences:geofence-list"))
        ids = {row["id"] for row in response.json()["data"]["results"]}
        assert ids == {circle_geofence.pk}

    def test_presence_list_is_scoped(
        self, admin_client, organization, other_organization, circle_geofence, foreign_geofence
    ):
        today = timezone.now().date()
        mine = UserFactory(organization=organization)
        theirs = UserFactory(organization=other_organization)
        Presence.objects.create(
            user=mine, organization=organization, geofence=circle_geofence, date=today
        )
        Presence.objects.create(
            user=theirs,
            organization=other_organization,
            geofence=foreign_geofence,
            date=today,
        )

        response = admin_client.get(reverse("presence:admin-presence"))
        user_ids = {row["user_id"] for row in response.json()["data"]["results"]}
        assert user_ids == {mine.pk}

    def test_user_directory_is_scoped(self, admin_client, foreign_user):
        response = admin_client.get(reverse("auth:user-list"))
        emails = {row["email"] for row in response.json()["data"]["results"]}
        assert foreign_user.email not in emails

    def test_organization_list_shows_only_your_own(
        self, user_client, organization, other_organization
    ):
        response = user_client.get(reverse("organizations:organization-list"))
        codes = {row["code"] for row in response.json()["data"]["results"]}
        assert codes == {organization.code}


class TestEvaluationScoping:
    def test_a_user_is_never_evaluated_against_a_foreign_geofence(
        self, organization, other_organization, foreign_geofence
    ):
        """Two organizations can cover the same physical place."""
        results = evaluate_point(
            organization_id=organization.pk,
            latitude=CENTRE[0],
            longitude=CENTRE[1],
            accuracy=10,
        )
        assert results == []

    def test_a_fix_only_affects_the_users_own_organization(
        self, user, foreign_user, circle_geofence, foreign_geofence, submit_location
    ):
        now = timezone.now()
        for index in range(2):
            submit_location(
                user,
                latitude=CENTRE[0],
                longitude=CENTRE[1],
                recorded_at=now - timedelta(seconds=60 - 60 * index),
            )
        assert Presence.objects.filter(geofence=foreign_geofence).count() == 0
        assert Presence.objects.filter(geofence=circle_geofence).count() == 1


class TestCrossOrganizationWrites:
    def test_an_admin_cannot_create_a_geofence_elsewhere(
        self, admin_client, organization, other_organization
    ):
        response = admin_client.post(
            reverse("geofences:geofence-list"),
            {
                "name": "Sneaky",
                "type": "CIRCLE",
                "latitude": CENTRE[0],
                "longitude": CENTRE[1],
                "radius": 150,
                "organization": other_organization.pk,
            },
            format="json",
        )
        assert response.status_code == 201
        from geofences.models import Geofence

        assert (
            Geofence.objects.get(pk=response.json()["data"]["id"]).organization_id
            == organization.pk
        )

    def test_an_admin_cannot_modify_a_foreign_geofence(
        self, admin_client, foreign_geofence
    ):
        response = admin_client.patch(
            reverse("geofences:geofence-detail", args=[foreign_geofence.pk]),
            {"is_active": False},
            format="json",
        )
        assert response.status_code == 404
        foreign_geofence.refresh_from_db()
        assert foreign_geofence.is_active is True

    def test_a_member_of_an_inactive_organization_is_locked_out(
        self, user_client, organization
    ):
        organization.is_active = False
        organization.save(update_fields=["is_active"])
        response = user_client.get(reverse("presence:presence-me"))
        assert response.status_code == 403


class TestPlatformAdmin:
    def test_platform_admin_sees_every_organization(
        self, as_user, platform_admin, organization, other_organization
    ):
        response = as_user(platform_admin).get(
            reverse("organizations:organization-list")
        )
        codes = {row["code"] for row in response.json()["data"]["results"]}
        assert {organization.code, other_organization.code} <= codes

    def test_platform_admin_can_narrow_to_one_organization(
        self, as_user, platform_admin, organization, circle_geofence, foreign_geofence
    ):
        response = as_user(platform_admin).get(
            reverse("geofences:geofence-list"), {"organization": organization.pk}
        )
        ids = {row["id"] for row in response.json()["data"]["results"]}
        assert ids == {circle_geofence.pk}
