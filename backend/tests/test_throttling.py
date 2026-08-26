"""Rate limiting behaviour, including what happens when the backend is down."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from tests.factories import DEFAULT_PASSWORD

pytestmark = pytest.mark.django_db

#: A Redis that is not listening, standing in for an outage.
UNREACHABLE_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://127.0.0.1:6399/0",
    }
}


def rates(**overrides: str) -> dict:
    """The project's REST_FRAMEWORK settings with different throttle rates."""
    return {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {
            **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
            **overrides,
        },
    }


class TestFailOpen:
    """A cache outage must not take the API down.

    Throttling is a protection mechanism, not a correctness one; losing it for
    the duration of an outage is far better than returning 500 to every caller.
    """

    def test_login_works_while_the_throttle_backend_is_unreachable(
        self, api_client, user
    ):
        with override_settings(CACHES=UNREACHABLE_CACHE):
            response = api_client.post(
                reverse("auth:login"),
                {"email": user.email, "password": DEFAULT_PASSWORD},
            )
        assert response.status_code == 200

    def test_location_update_works_while_the_backend_is_unreachable(
        self, user_client, circle_geofence, campus_centre
    ):
        with override_settings(CACHES=UNREACHABLE_CACHE):
            response = user_client.post(
                reverse("locations:location-update"),
                {
                    "latitude": campus_centre[0],
                    "longitude": campus_centre[1],
                    "accuracy": 12,
                    "recorded_at": timezone.now().isoformat(),
                },
                format="json",
            )
        assert response.status_code == 201


class TestEnforcement:
    def test_login_attempts_are_rate_limited(self, api_client, user):
        with override_settings(REST_FRAMEWORK=rates(auth="2/min")):
            for _ in range(2):
                api_client.post(
                    reverse("auth:login"),
                    {"email": user.email, "password": "wrong-password"},
                )
            blocked = api_client.post(
                reverse("auth:login"),
                {"email": user.email, "password": DEFAULT_PASSWORD},
            )
        assert blocked.status_code == 429

    def test_location_updates_are_rate_limited_per_user(
        self, as_user, user, other_user, circle_geofence, campus_centre
    ):
        def send(account, seconds_ago: int):
            return as_user(account).post(
                reverse("locations:location-update"),
                {
                    "latitude": campus_centre[0],
                    "longitude": campus_centre[1],
                    "accuracy": 12,
                    "recorded_at": (
                        timezone.now() - timedelta(seconds=seconds_ago)
                    ).isoformat(),
                },
                format="json",
            )

        with override_settings(REST_FRAMEWORK=rates(location_update="2/min")):
            assert send(user, 30).status_code == 201
            assert send(user, 20).status_code == 201
            assert send(user, 10).status_code == 429
            # A different user has their own bucket: the limit is per account,
            # not per IP, because a whole campus shares one NAT address.
            assert send(other_user, 30).status_code == 201
