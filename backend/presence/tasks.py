"""Periodic presence maintenance.

The stale sweep is the reason this project needs Celery at all: presence has to
decay on its own, without anybody sending a request.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction

from common.conf import geo_conf
from common.utils.time import utc_now
from presence.models import PresenceEvent
from presence.services.staleness import (
    close_abandoned_presence_days,
    detect_stale_presences,
)

logger = logging.getLogger("geofencing.presence")

PURGE_CHUNK_SIZE = 5_000


@shared_task(name="presence.tasks.detect_stale_presence")
def detect_stale_presence(batch_size: int = 500) -> dict[str, int]:
    """Mark PRESENT users whose device stopped reporting as STALE.

    Runs every minute. Never marks anybody GONE: the task cannot distinguish a
    user who left from a user whose phone locked, so it reports uncertainty
    instead of inventing a departure.
    """
    result = detect_stale_presences(batch_size=batch_size)
    if result.transitioned:
        logger.info("Stale sweep: %s rows transitioned", result.transitioned)
    return result.as_dict()


@shared_task(name="presence.tasks.close_abandoned_presence_days")
def close_abandoned_presence_days_task(batch_size: int = 500) -> dict[str, int]:
    """Close attendance days that ended while the user was still checked in."""
    return close_abandoned_presence_days(batch_size=batch_size).as_dict()


@shared_task(name="presence.tasks.purge_expired_presence_events")
def purge_expired_presence_events() -> dict[str, int]:
    """Apply the presence-event retention policy.

    Attendance history is kept much longer than raw coordinates: it is the
    business record, and it contains far less positional detail.
    """
    cutoff = utc_now() - timedelta(days=geo_conf.PRESENCE_EVENT_RETENTION_DAYS)
    deleted_total = 0
    while True:
        ids = list(
            PresenceEvent.objects.filter(timestamp__lt=cutoff)
            .order_by("id")
            .values_list("id", flat=True)[:PURGE_CHUNK_SIZE]
        )
        if not ids:
            break
        with transaction.atomic():
            deleted, _ = PresenceEvent.objects.filter(id__in=ids).delete()
        deleted_total += deleted
        if len(ids) < PURGE_CHUNK_SIZE:
            break

    logger.info("Retention purge removed %s presence events", deleted_total)
    return {"presence_events_deleted": deleted_total, "cutoff": cutoff.isoformat()}
