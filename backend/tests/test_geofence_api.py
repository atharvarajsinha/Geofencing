"""Geofence API: permissions, tenancy and the wire format."""
from __future__ import annotations

import pytest
from django.urls import reverse

from geofences.models import Geofence
from tests.factories import CAMPUS_LATITUDE, CAMPUS_LONGITUDE, CircleGeofenceFactory

pytestmark = pytest.mark.django_db

CIRCLE_PAYLOAD = {
    "name": "College Campus",
    "type": "CIRCLE",
    "latitude": CAMPUS_LATITUDE,
    "longitude": CAMPUS_LONGITUDE,
    "radius": 150,
}

RECTANGLE_PAYLOAD = {
    "name": "College Campus Rectangle",
    "type": "RECTANGLE",
    "min_latitude": 29.5971,
    "max_latitude": 29.5983,
    "min_longitude": 79.6581,
    "max_longitude": 79.6601,
}


def list_url() -> str:
    return reverse("geofences:geofence-list")


def detail_url(pk: int) -> str:
    return reverse("geofences:geofence-detail", args=[pk])


class TestCreate:
    def test_admin_creates_a_circle(self, admin_client, organization):
        response = admin_client.post(list_url(), CIRCLE_PAYLOAD, format="json")
        assert response.status_code == 201, response.json()
        data = response.json()["data"]
        assert data["type"] == "CIRCLE"
        assert data["latitude"] == pytest.approx(CAMPUS_LATITUDE)
        assert data["effective_thresholds"]["entry_threshold_m"] == 150.0
        assert data["effective_thresholds"]["exit_threshold_m"] == 190.0
        assert Geofence.objects.get(pk=data["id"]).organization_id == organization.pk

    def test_admin_creates_a_rectangle(self, admin_client):
        response = admin_client.post(list_url(), RECTANGLE_PAYLOAD, format="json")
        assert response.status_code == 201, response.json()
        data = response.json()["data"]
        assert data["type"] == "RECTANGLE"
        assert data["min_latitude"] == pytest.approx(29.5971)
        assert data["max_longitude"] == pytest.approx(79.6601)
        assert data["radius"] is None
        # Convenience aliases point at the centre of the box.
        assert data["latitude"] == pytest.approx((29.5971 + 29.5983) / 2)

    def test_inverted_rectangle_is_rejected(self, admin_client):
        payload = {
            **RECTANGLE_PAYLOAD,
            "min_latitude": 29.5983,
            "max_latitude": 29.5971,
        }
        response = admin_client.post(list_url(), payload, format="json")
        assert response.status_code == 400
        assert "max_latitude" in response.json()["errors"]

    def test_rectangle_missing_an_edge_is_rejected(self, admin_client):
        payload = {
            key: value
            for key, value in RECTANGLE_PAYLOAD.items()
            if key != "max_longitude"
        }
        response = admin_client.post(list_url(), payload, format="json")
        assert response.status_code == 400
        assert "max_longitude" in response.json()["errors"]

    def test_circle_payload_may_not_carry_bounding_edges(self, admin_client):
        """The envelope of a circle is derived, never client-supplied."""
        response = admin_client.post(
            list_url(), {**CIRCLE_PAYLOAD, "min_latitude": 0.0}, format="json"
        )
        assert response.status_code == 400
        assert "min_latitude" in response.json()["errors"]

    def test_circle_without_radius_is_rejected(self, admin_client):
        payload = {key: value for key, value in CIRCLE_PAYLOAD.items() if key != "radius"}
        response = admin_client.post(list_url(), payload, format="json")
        assert response.status_code == 400
        assert "radius" in response.json()["errors"]

    def test_rectangle_payload_may_not_carry_a_radius(self, admin_client):
        response = admin_client.post(
            list_url(), {**RECTANGLE_PAYLOAD, "radius": 100}, format="json"
        )
        assert response.status_code == 400

    def test_exit_radius_must_exceed_entry_radius(self, admin_client):
        response = admin_client.post(
            list_url(),
            {**CIRCLE_PAYLOAD, "entry_radius": 120, "exit_radius": 80},
            format="json",
        )
        assert response.status_code == 400
        assert "exit_radius" in response.json()["errors"]

    def test_custom_hysteresis_is_stored(self, admin_client):
        response = admin_client.post(
            list_url(),
            {**CIRCLE_PAYLOAD, "entry_radius": 80, "exit_radius": 120},
            format="json",
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["entry_radius"] == 80
        assert data["exit_radius"] == 120


class TestPermissions:
    def test_anonymous_cannot_list(self, api_client):
        assert api_client.get(list_url()).status_code == 401

    def test_member_can_list(self, user_client, circle_geofence):
        response = user_client.get(list_url())
        assert response.status_code == 200
        assert response.json()["data"]["count"] == 1

    def test_member_cannot_create(self, user_client):
        response = user_client.post(list_url(), CIRCLE_PAYLOAD, format="json")
        assert response.status_code == 403

    def test_member_cannot_delete(self, user_client, circle_geofence):
        assert user_client.delete(detail_url(circle_geofence.pk)).status_code == 403

    def test_admin_can_patch(self, admin_client, circle_geofence):
        response = admin_client.patch(
            detail_url(circle_geofence.pk), {"name": "Renamed"}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Renamed"

    def test_admin_can_deactivate(self, admin_client, circle_geofence):
        response = admin_client.patch(
            detail_url(circle_geofence.pk), {"is_active": False}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["data"]["is_active"] is False

    def test_admin_can_delete_an_unused_geofence(self, admin_client, circle_geofence):
        assert admin_client.delete(detail_url(circle_geofence.pk)).status_code == 204
        assert not Geofence.objects.filter(pk=circle_geofence.pk).exists()


class TestTenancy:
    def test_list_never_leaks_another_organization(
        self, admin_client, organization, other_organization
    ):
        CircleGeofenceFactory(organization=organization, name="Mine")
        CircleGeofenceFactory(organization=other_organization, name="Theirs")

        response = admin_client.get(list_url())
        names = {row["name"] for row in response.json()["data"]["results"]}
        assert names == {"Mine"}

    def test_retrieving_a_foreign_geofence_is_a_404_not_a_403(
        self, admin_client, other_organization
    ):
        foreign = CircleGeofenceFactory(organization=other_organization)
        # 404 rather than 403: existence itself is confidential.
        assert admin_client.get(detail_url(foreign.pk)).status_code == 404

    def test_patching_a_foreign_geofence_is_rejected(
        self, admin_client, other_organization
    ):
        foreign = CircleGeofenceFactory(organization=other_organization)
        response = admin_client.patch(
            detail_url(foreign.pk), {"name": "Hijacked"}, format="json"
        )
        assert response.status_code == 404
        foreign.refresh_from_db()
        assert foreign.name != "Hijacked"

    def test_deleting_a_foreign_geofence_is_rejected(
        self, admin_client, other_organization
    ):
        foreign = CircleGeofenceFactory(organization=other_organization)
        assert admin_client.delete(detail_url(foreign.pk)).status_code == 404
        assert Geofence.objects.filter(pk=foreign.pk).exists()

    def test_a_new_geofence_always_lands_in_the_callers_organization(
        self, admin_client, organization, other_organization
    ):
        response = admin_client.post(
            list_url(),
            {**CIRCLE_PAYLOAD, "organization": other_organization.pk},
            format="json",
        )
        assert response.status_code == 201
        created = Geofence.objects.get(pk=response.json()["data"]["id"])
        assert created.organization_id == organization.pk

    def test_platform_admin_must_name_the_target_organization(
        self, as_user, platform_admin
    ):
        client = as_user(platform_admin)
        response = client.post(list_url(), CIRCLE_PAYLOAD, format="json")
        assert response.status_code == 400
        assert "organization" in response.json()["errors"]

    def test_platform_admin_can_create_for_a_named_organization(
        self, as_user, platform_admin, organization
    ):
        client = as_user(platform_admin)
        response = client.post(
            list_url(), {**CIRCLE_PAYLOAD, "organization": organization.pk}, format="json"
        )
        assert response.status_code == 201
        assert (
            Geofence.objects.get(pk=response.json()["data"]["id"]).organization_id
            == organization.pk
        )


class TestFiltering:
    def test_filter_by_type(self, admin_client, circle_geofence, rectangle_geofence):
        response = admin_client.get(list_url(), {"type": "RECTANGLE"})
        results = response.json()["data"]["results"]
        assert [row["id"] for row in results] == [rectangle_geofence.pk]

    def test_filter_by_active_flag(self, admin_client, circle_geofence):
        circle_geofence.is_active = False
        circle_geofence.save(update_fields=["is_active"])
        assert admin_client.get(list_url(), {"is_active": "true"}).json()["data"]["count"] == 0
        assert admin_client.get(list_url(), {"is_active": "false"}).json()["data"]["count"] == 1
