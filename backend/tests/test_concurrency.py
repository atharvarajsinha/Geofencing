"""Concurrent delivery of location updates.

These need real transactions (``transaction=True``) because the protection they
exercise - a per-user advisory lock plus row locking - only exists at the
database level.
"""
from __future__ import annotations

from datetime import timedelta
from threading import Thread

import pytest
from django.db import connections
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from locations.models import LocationUpdate
from presence.enums import PresenceEventType, PresenceStatus
from presence.models import Presence, PresenceEvent
from tests.conftest import offset_point
from tests.factories import CircleGeofenceFactory, OrganizationFactory, UserFactory

CENTRE = offset_point()
URL_NAME = "locations:location-update"


def body(recorded_at, *, client_event_id=None):
    payload = {
        "latitude": CENTRE[0],
        "longitude": CENTRE[1],
        "accuracy": 10,
        "recorded_at": recorded_at.isoformat(),
    }
    if client_event_id:
        payload["client_event_id"] = client_event_id
    return payload


def post_in_thread(account, payload, sink: list) -> Thread:
    def worker() -> None:
        try:
            client = APIClient()
            client.force_authenticate(user=account)
            response = client.post(reverse(URL_NAME), payload, format="json")
            sink.append(response.status_code)
        finally:
            # Each thread owns its connection; leaking one wedges teardown.
            connections.close_all()

    return Thread(target=worker)


def run_together(threads: list[Thread]) -> None:
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)


@pytest.mark.django_db(transaction=True)
class TestConcurrentUpdates:
    def _setup(self):
        organization = OrganizationFactory()
        user = UserFactory(organization=organization)
        geofence = CircleGeofenceFactory(organization=organization)
        return organization, user, geofence

    def test_simultaneous_retries_store_exactly_one_update(self):
        _, user, _geofence = self._setup()
        payload = body(timezone.now() - timedelta(seconds=5), client_event_id="retry-1")

        statuses: list[int] = []
        run_together([post_in_thread(user, payload, statuses) for _ in range(2)])

        assert sorted(statuses) == [200, 201]
        assert LocationUpdate.objects.filter(user=user).count() == 1

    def test_simultaneous_distinct_fixes_produce_one_check_in(self):
        _, user, _geofence = self._setup()
        now = timezone.now()

        # First reading: streak = 1.
        first = APIClient()
        first.force_authenticate(user=user)
        first.post(reverse(URL_NAME), body(now - timedelta(seconds=120)), format="json")

        statuses: list[int] = []
        run_together(
            [
                post_in_thread(user, body(now - timedelta(seconds=60)), statuses),
                post_in_thread(user, body(now), statuses),
            ]
        )

        assert LocationUpdate.objects.filter(user=user).count() == 3
        presence = Presence.objects.get(user=user)
        assert presence.status == PresenceStatus.PRESENT
        # The lock serialises the two requests, so ENTERED happens exactly once.
        assert (
            PresenceEvent.objects.filter(
                user=user, event_type=PresenceEventType.ENTERED
            ).count()
            == 1
        )

    def test_no_duplicate_presence_row_is_created(self):
        _, user, geofence = self._setup()
        now = timezone.now()

        statuses: list[int] = []
        run_together(
            [
                post_in_thread(user, body(now - timedelta(seconds=30)), statuses),
                post_in_thread(user, body(now), statuses),
            ]
        )

        assert (
            Presence.objects.filter(user=user, geofence=geofence).count() == 1
        ), "the unique constraint plus the advisory lock must keep this at one row"
