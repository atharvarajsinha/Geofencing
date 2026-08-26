"""Timeout driven transitions: STALE detection and day rollover.

Nothing in this module can produce a ``GONE`` from silence. A device that stops
reporting - screen locked, browser closed, tunnel, dead battery - is reported as
``STALE``, which says exactly what is true: we no longer know.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Min, Q

from common.conf import geo_conf
from common.utils.time import day_bounds_utc, local_date, utc_now
from geofences.models import Geofence
from presence.enums import PresenceStatus
from presence.models import Presence, PresenceEvent
from presence.services.state_machine import (
    PresenceState,
    apply_day_rollover,
    apply_timeout,
)

logger = logging.getLogger("geofencing.presence")

DEFAULT_BATCH_SIZE = 500


@dataclass
class SweepResult:
    scanned: int = 0
    transitioned: int = 0

    def as_dict(self) -> dict[str, int]:
        return {"scanned": self.scanned, "transitioned": self.transitioned}


def _minimum_stale_timeout_seconds() -> int:
    """Smallest timeout in use, so the candidate query cannot miss a row."""
    override_minimum = Geofence.objects.filter(
        is_active=True, stale_after_seconds__isnull=False
    ).aggregate(value=Min("stale_after_seconds"))["value"]
    if override_minimum is None:
        return int(geo_conf.STALE_AFTER_SECONDS)
    return int(min(override_minimum, geo_conf.STALE_AFTER_SECONDS))


def _state(presence: Presence) -> PresenceState:
    return PresenceState(
        status=presence.status,
        consecutive_inside=presence.consecutive_inside,
        consecutive_outside=presence.consecutive_outside,
        last_reading_at=presence.last_reading_at,
        has_checked_in=presence.check_in_at is not None,
    )


def detect_stale_presences(
    *, now: datetime | None = None, batch_size: int = DEFAULT_BATCH_SIZE
) -> SweepResult:
    """Mark PRESENT rows whose device has gone quiet as STALE."""
    now = now or utc_now()
    result = SweepResult()

    coarse_cutoff = now - timedelta(seconds=_minimum_stale_timeout_seconds())
    candidate_ids = list(
        Presence.objects.filter(status=PresenceStatus.PRESENT)
        .filter(Q(last_seen_at__isnull=True) | Q(last_seen_at__lt=coarse_cutoff))
        .order_by("id")
        .values_list("id", flat=True)[:batch_size]
    )

    for presence_id in candidate_ids:
        result.scanned += 1
        with transaction.atomic():
            presence = (
                Presence.objects.select_for_update()
                .select_related("geofence")
                .filter(pk=presence_id)
                .first()
            )
            if presence is None or presence.status != PresenceStatus.PRESENT:
                # A location update landed while we were scanning: leave it alone.
                continue

            timeout = presence.geofence.effective_stale_after_seconds
            reference = presence.last_seen_at
            if reference is not None and (now - reference).total_seconds() < timeout:
                continue

            decision = apply_timeout(_state(presence))
            if not decision.applied:
                continue

            presence.status = decision.status
            presence.consecutive_inside = decision.consecutive_inside
            presence.consecutive_outside = decision.consecutive_outside
            presence.stale_since = now
            presence.save(
                update_fields=[
                    "status",
                    "consecutive_inside",
                    "consecutive_outside",
                    "stale_since",
                    "updated_at",
                ]
            )

            for event_type, reason in decision.events:
                PresenceEvent.objects.get_or_create(
                    presence=presence,
                    event_type=event_type,
                    timestamp=now,
                    defaults={
                        "user_id": presence.user_id,
                        "organization_id": presence.organization_id,
                        "geofence_id": presence.geofence_id,
                        "reason": reason,
                        "previous_status": PresenceStatus.PRESENT,
                        "new_status": decision.status,
                        "latitude": presence.last_latitude,
                        "longitude": presence.last_longitude,
                        "accuracy": presence.last_accuracy,
                        "metadata": {
                            "last_seen_at": (
                                reference.isoformat() if reference else None
                            ),
                            "timeout_seconds": timeout,
                            "note": (
                                "No location update within the timeout. The user is "
                                "not marked GONE: silence is not departure."
                            ),
                        },
                    },
                )
            result.transitioned += 1
            logger.info(
                "Presence %s marked STALE (last seen %s)", presence.pk, reference
            )

    return result


def close_abandoned_presence_days(
    *, now: datetime | None = None, batch_size: int = DEFAULT_BATCH_SIZE
) -> SweepResult:
    """Close rows still PRESENT after their attendance day ended.

    The EXITED event is timestamped with the last moment we actually saw the
    user, and tagged ``DAY_ROLLOVER`` so reports never mistake it for an
    observed departure.
    """
    now = now or utc_now()
    result = SweepResult()

    candidates = (
        Presence.objects.filter(status=PresenceStatus.PRESENT)
        .select_related("organization")
        .order_by("id")[:batch_size]
    )

    for candidate in candidates:
        today = local_date(now, candidate.organization.timezone)
        if candidate.date >= today:
            continue

        result.scanned += 1
        with transaction.atomic():
            presence = (
                Presence.objects.select_for_update().filter(pk=candidate.pk).first()
            )
            if presence is None or presence.status != PresenceStatus.PRESENT:
                continue

            decision = apply_day_rollover(_state(presence))
            if not decision.applied:
                continue

            _, day_end = day_bounds_utc(presence.date, candidate.organization.timezone)
            closed_at = presence.last_seen_at or day_end

            presence.status = decision.status
            presence.consecutive_inside = decision.consecutive_inside
            presence.consecutive_outside = decision.consecutive_outside
            presence.check_out_at = closed_at
            presence.save(
                update_fields=[
                    "status",
                    "consecutive_inside",
                    "consecutive_outside",
                    "check_out_at",
                    "updated_at",
                ]
            )

            for event_type, reason in decision.events:
                PresenceEvent.objects.get_or_create(
                    presence=presence,
                    event_type=event_type,
                    timestamp=closed_at,
                    defaults={
                        "user_id": presence.user_id,
                        "organization_id": presence.organization_id,
                        "geofence_id": presence.geofence_id,
                        "reason": reason,
                        "previous_status": PresenceStatus.PRESENT,
                        "new_status": decision.status,
                        "latitude": presence.last_latitude,
                        "longitude": presence.last_longitude,
                        "accuracy": presence.last_accuracy,
                        "metadata": {
                            "note": "Attendance day ended while the user was checked in.",
                        },
                    },
                )
            result.transitioned += 1

    return result
