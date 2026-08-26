"""Read-side queries for location history."""
from __future__ import annotations

from datetime import datetime, timedelta

from django.db.models import QuerySet

from common.utils.time import utc_now
from locations.models import LocationAnomaly, LocationUpdate


def last_update_for_user(user_id: int) -> LocationUpdate | None:
    """Most recent fix by device time, trusted or not."""
    return LocationUpdate.objects.for_user(user_id).newest_first().first()


def last_trusted_update_for_user(
    user_id: int, *, before: datetime | None = None
) -> LocationUpdate | None:
    """Most recent trusted fix, optionally strictly before a given instant.

    Anomaly detection compares against the last *trusted* fix so that one
    teleporting reading cannot poison the comparison for every reading after it.
    """
    queryset = LocationUpdate.objects.for_user(user_id).trusted()
    if before is not None:
        queryset = queryset.filter(recorded_at__lt=before)
    return queryset.newest_first().first()


def count_recent_updates(user_id: int, *, seconds: int, now: datetime | None = None) -> int:
    now = now or utc_now()
    return LocationUpdate.objects.for_user(user_id).filter(
        received_at__gte=now - timedelta(seconds=seconds)
    ).count()


def find_replay(
    *, user_id: int, client_event_id: str | None, recorded_at: datetime
) -> LocationUpdate | None:
    """Locate a previously accepted copy of this observation.

    Two mechanisms, in order of reliability:

    1. the client supplied ``client_event_id`` - an exact idempotency key,
    2. otherwise an identical ``recorded_at`` for the same user, which can only
       happen when the same fix is delivered twice.
    """
    if client_event_id:
        return LocationUpdate.objects.filter(
            user_id=user_id, client_event_id=client_event_id
        ).first()
    return LocationUpdate.objects.filter(
        user_id=user_id, recorded_at=recorded_at
    ).first()


def user_location_history(user_id: int) -> QuerySet[LocationUpdate]:
    return LocationUpdate.objects.for_user(user_id).newest_first()


def organization_anomalies(organization_id: int) -> QuerySet[LocationAnomaly]:
    return (
        LocationAnomaly.objects.filter(organization_id=organization_id)
        .select_related("user", "location_update")
        .order_by("-created_at")
    )


def recent_identical_reading_count(
    *, user_id: int, latitude: float, longitude: float, since: datetime, tolerance: float
) -> int:
    """How many recent fixes sit within ``tolerance`` degrees of this one.

    A degree-space comparison is deliberate: this is a cheap pre-filter for the
    "device has not moved a millimetre in an hour" pattern, not a distance
    measurement.
    """
    delta = tolerance / 111_320.0  # metres -> degrees, good enough for a pre-filter
    return (
        LocationUpdate.objects.for_user(user_id)
        .filter(
            recorded_at__gte=since,
            latitude__gte=latitude - delta,
            latitude__lte=latitude + delta,
            longitude__gte=longitude - delta,
            longitude__lte=longitude + delta,
        )
        .count()
    )
