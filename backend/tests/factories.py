"""Test data factories."""
from __future__ import annotations

import factory

from accounts.enums import UserRole
from accounts.models import User
from common.utils.geo import (
    METRES_PER_DEGREE_LATITUDE,
    metres_per_degree_longitude,
)
from geofences.enums import GeofenceType
from geofences.models import Geofence
from organizations.models import Organization

#: A fixed reference location so no test invents its own coordinates.
CAMPUS_LATITUDE = 29.5976
CAMPUS_LONGITUDE = 79.6591

DEFAULT_PASSWORD = "TestPassw0rd!2026"


class OrganizationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organization

    name = factory.Sequence(lambda n: f"Organization {n}")
    code = factory.Sequence(lambda n: f"ORG{n:04d}")
    timezone = "UTC"
    is_active = True


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    name = factory.Sequence(lambda n: f"User {n}")
    role = UserRole.USER
    organization = factory.SubFactory(OrganizationFactory)
    is_active = True

    @factory.post_generation
    def password(self, create: bool, extracted: str | None, **kwargs) -> None:
        if not create:
            return
        self.set_password(extracted or DEFAULT_PASSWORD)
        self.save(update_fields=["password"])


class AdminUserFactory(UserFactory):
    """The super admin, owning one organization.

    Only one ``ADMIN`` row may exist at a time (``only_one_admin_account``), so
    a single test must not build two of these -- or one of these and a
    :class:`PlatformAdminFactory`.
    """

    role = UserRole.ADMIN
    email = factory.Sequence(lambda n: f"admin{n}@example.com")


class PlatformAdminFactory(AdminUserFactory):
    """The super admin as a platform operator: no organization, crosses tenants."""

    organization = None
    is_staff = True
    email = factory.Sequence(lambda n: f"root{n}@example.com")


class CircleGeofenceFactory(factory.django.DjangoModelFactory):
    """A 150 m circle: entry threshold 150 m, exit threshold 190 m."""

    class Meta:
        model = Geofence

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Campus {n}")
    geofence_type = GeofenceType.CIRCLE
    center_latitude = CAMPUS_LATITUDE
    center_longitude = CAMPUS_LONGITUDE
    radius = 150.0
    # Overwritten by Geofence.save(), which derives the envelope from the
    # centre and radius. Present so the NOT NULL columns have a value.
    min_latitude = CAMPUS_LATITUDE
    max_latitude = CAMPUS_LATITUDE
    min_longitude = CAMPUS_LONGITUDE
    max_longitude = CAMPUS_LONGITUDE
    entry_radius = 150.0
    exit_radius = 190.0
    is_active = True


def campus_bbox(half_side_m: float = 200.0) -> dict[str, float]:
    """A square box centred on the campus, roughly ``half_side_m`` per side."""
    d_lat = half_side_m / METRES_PER_DEGREE_LATITUDE
    d_lon = half_side_m / metres_per_degree_longitude(CAMPUS_LATITUDE)
    return {
        "min_latitude": CAMPUS_LATITUDE - d_lat,
        "max_latitude": CAMPUS_LATITUDE + d_lat,
        "min_longitude": CAMPUS_LONGITUDE - d_lon,
        "max_longitude": CAMPUS_LONGITUDE + d_lon,
    }


class RectangleGeofenceFactory(factory.django.DjangoModelFactory):
    """A ~400 m square with a 0 m entry inset and a 40 m exit outset."""

    class Meta:
        model = Geofence

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Block {n}")
    geofence_type = GeofenceType.RECTANGLE
    min_latitude = factory.LazyFunction(lambda: campus_bbox()["min_latitude"])
    max_latitude = factory.LazyFunction(lambda: campus_bbox()["max_latitude"])
    min_longitude = factory.LazyFunction(lambda: campus_bbox()["min_longitude"])
    max_longitude = factory.LazyFunction(lambda: campus_bbox()["max_longitude"])
    entry_radius = 0.0
    exit_radius = 40.0
    is_active = True
