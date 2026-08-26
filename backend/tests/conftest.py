"""Shared pytest fixtures.

The suite needs a real PostgreSQL + PostGIS database: the geofence evaluator is
SQL, and testing it against a mock would only prove the mock works. See
README.md for the one-line Docker command that provides one.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from math import cos, radians
from typing import Any, Callable

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from tests.factories import (
    CAMPUS_LATITUDE,
    CAMPUS_LONGITUDE,
    AdminUserFactory,
    CircleGeofenceFactory,
    OrganizationFactory,
    PlatformAdminFactory,
    RectangleGeofenceFactory,
    UserFactory,
)

METRES_PER_DEGREE_LATITUDE = 111_320.0


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def offset_point(
    metres_north: float = 0.0,
    metres_east: float = 0.0,
    *,
    latitude: float = CAMPUS_LATITUDE,
    longitude: float = CAMPUS_LONGITUDE,
) -> tuple[float, float]:
    """A coordinate offset from the campus centre by a known distance."""
    d_lat = metres_north / METRES_PER_DEGREE_LATITUDE
    d_lon = metres_east / (METRES_PER_DEGREE_LATITUDE * cos(radians(latitude)))
    return latitude + d_lat, longitude + d_lon


@pytest.fixture
def campus_centre() -> tuple[float, float]:
    return CAMPUS_LATITUDE, CAMPUS_LONGITUDE


@pytest.fixture
def point_at() -> Callable[..., tuple[float, float]]:
    return offset_point


# ---------------------------------------------------------------------------
# Tenancy fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def organization(db):
    return OrganizationFactory(name="Sitare University", code="SITARE")


@pytest.fixture
def other_organization(db):
    return OrganizationFactory(name="Other College", code="OTHER")


@pytest.fixture
def user(db, organization):
    return UserFactory(organization=organization, email="member@example.com")


@pytest.fixture
def other_user(db, organization):
    return UserFactory(organization=organization, email="member2@example.com")


@pytest.fixture
def admin_user(db, organization):
    return AdminUserFactory(organization=organization, email="admin@example.com")


@pytest.fixture
def foreign_admin(db, other_organization):
    return AdminUserFactory(
        organization=other_organization, email="foreign-admin@example.com"
    )


@pytest.fixture
def platform_admin(db):
    return PlatformAdminFactory(email="root@example.com")


# ---------------------------------------------------------------------------
# Geofence fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def circle_geofence(db, organization):
    """150 m radius; INSIDE at <= 150 m, OUTSIDE at >= 190 m."""
    return CircleGeofenceFactory(organization=organization, name="Campus")


@pytest.fixture
def rectangle_geofence(db, organization):
    return RectangleGeofenceFactory(organization=organization, name="Main Block")


# ---------------------------------------------------------------------------
# API clients
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def clear_cache():
    """Throttle counters live in the cache; never let them leak between tests."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def as_user() -> Callable[[Any], APIClient]:
    """Return an APIClient authenticated as the given user."""

    def _login(account) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=account)
        return client

    return _login


@pytest.fixture
def user_client(as_user, user) -> APIClient:
    return as_user(user)


@pytest.fixture
def admin_client(as_user, admin_user) -> APIClient:
    return as_user(admin_user)


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def now() -> datetime:
    return timezone.now()


@pytest.fixture
def reading_times(now) -> Callable[[int, int], list[datetime]]:
    """``reading_times(3)`` -> three timestamps one minute apart, ending now."""

    def _times(count: int, spacing_seconds: int = 60) -> list[datetime]:
        return [
            now - timedelta(seconds=spacing_seconds * (count - index - 1))
            for index in range(count)
        ]

    return _times


# ---------------------------------------------------------------------------
# Ingest helper
# ---------------------------------------------------------------------------
@pytest.fixture
def submit_location():
    """Send one fix through the full service pipeline (no HTTP layer)."""
    from locations.validators import LocationPayload
    from presence.services.processing import process_location_update

    def _submit(
        account,
        *,
        latitude: float,
        longitude: float,
        accuracy: float = 10.0,
        recorded_at: datetime | None = None,
        client_event_id: str | None = None,
    ):
        payload = LocationPayload(
            latitude=latitude,
            longitude=longitude,
            accuracy=accuracy,
            recorded_at=recorded_at or timezone.now(),
            client_event_id=client_event_id,
        )
        return process_location_update(user=account, payload=payload)

    return _submit
