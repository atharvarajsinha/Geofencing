"""Location related background work."""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction

from common.conf import geo_conf
from common.utils.time import utc_now
from locations.models import LocationAnomaly, LocationUpdate

logger = logging.getLogger("geofencing.locations")

#: Delete in chunks so a first run on a large table cannot lock it for minutes.
PURGE_CHUNK_SIZE = 5_000


def _purge(queryset, *, chunk_size: int = PURGE_CHUNK_SIZE) -> int:
    deleted_total = 0
    while True:
        ids = list(queryset.values_list("id", flat=True)[:chunk_size])
        if not ids:
            return deleted_total
        with transaction.atomic():
            deleted, _ = queryset.model.objects.filter(id__in=ids).delete()
        deleted_total += deleted
        if len(ids) < chunk_size:
            return deleted_total


@shared_task(name="locations.tasks.purge_expired_location_history")
def purge_expired_location_history() -> dict[str, int]:
    """Enforce the location retention policy.

    Raw coordinates are the most sensitive data this system holds and the least
    useful once the day is closed, so they expire well before presence records
    do. See docs/PRIVACY.md.
    """
    now = utc_now()
    location_cutoff = now - timedelta(days=geo_conf.LOCATION_HISTORY_RETENTION_DAYS)
    anomaly_cutoff = now - timedelta(days=geo_conf.ANOMALY_RETENTION_DAYS)

    anomalies_deleted = _purge(
        LocationAnomaly.objects.filter(created_at__lt=anomaly_cutoff).order_by("id")
    )
    updates_deleted = _purge(
        LocationUpdate.objects.filter(received_at__lt=location_cutoff).order_by("id")
    )

    logger.info(
        "Retention purge removed %s location updates and %s anomalies",
        updates_deleted,
        anomalies_deleted,
    )
    return {
        "location_updates_deleted": updates_deleted,
        "anomalies_deleted": anomalies_deleted,
        "location_cutoff": location_cutoff.isoformat(),
    }
