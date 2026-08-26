"""Location ingest orchestration: raw fix in, authoritative presence out.

This is the only place where a location update mutates presence. It runs the
whole pipeline inside a single transaction protected by a per-user advisory
lock, so two updates from the same device - the classic "PWA retried while the
first request was still in flight" case - are processed strictly one after the
other and can never produce two check-ins, two events, or contradictory states.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from django.db import IntegrityError, transaction

from accounts.models import User
from common.conf import geo_conf
from common.db import LOCK_NAMESPACE_LOCATION_PROCESSING, advisory_xact_lock
from common.exceptions import ValidationFailed
from common.utils.time import local_date, utc_now
from geofences.evaluation import GeofenceEvaluation, evaluate_point
from geofences.models import Geofence
from locations import selectors as location_selectors
from locations import services as location_services
from locations.models import LocationUpdate
from locations.validators import LocationPayload
from presence.enums import PresenceEventType, PresenceStatus
from presence.models import Presence, PresenceEvent
from presence.services.state_machine import (
    PresenceState,
    ReadingContext,
    TransitionDecision,
    apply_reading,
)

logger = logging.getLogger("geofencing.presence")


@dataclass
class PresenceOutcome:
    """What happened to one presence row for one reading."""

    presence: Presence
    evaluation: GeofenceEvaluation
    previous_status: str
    status: str
    events: list[str] = field(default_factory=list)
    applied: bool = True
    skip_reason: str = ""

    @property
    def changed(self) -> bool:
        return self.previous_status != self.status


@dataclass
class LocationIngestResult:
    location_update: LocationUpdate
    duplicate: bool = False
    trusted: bool = True
    anomalies: list[Any] = field(default_factory=list)
    evaluations: list[GeofenceEvaluation] = field(default_factory=list)
    outcomes: list[PresenceOutcome] = field(default_factory=list)
    skipped_reason: str = ""

    @property
    def transitions(self) -> list[PresenceOutcome]:
        return [outcome for outcome in self.outcomes if outcome.changed]


def _presence_state(presence: Presence) -> PresenceState:
    return PresenceState(
        status=presence.status,
        consecutive_inside=presence.consecutive_inside,
        consecutive_outside=presence.consecutive_outside,
        last_reading_at=presence.last_reading_at,
        has_checked_in=presence.check_in_at is not None,
    )


def _write_event(
    *,
    presence: Presence,
    event_type: str,
    reason: str,
    previous_status: str,
    new_status: str,
    timestamp: datetime,
    latitude: float | None = None,
    longitude: float | None = None,
    accuracy: float | None = None,
    location_update: LocationUpdate | None = None,
    metadata: dict[str, Any] | None = None,
) -> PresenceEvent | None:
    """Append one transition to the audit trail.

    The unique constraint on ``(presence, event_type, timestamp)`` is the last
    line of defence against duplicate events; hitting it means the same
    transition was computed twice, which is worth a log line but not an error
    for the client.
    """
    try:
        with transaction.atomic():
            return PresenceEvent.objects.create(
                user_id=presence.user_id,
                organization_id=presence.organization_id,
                geofence_id=presence.geofence_id,
                presence=presence,
                location_update=location_update,
                event_type=event_type,
                reason=reason,
                previous_status=previous_status,
                new_status=new_status,
                latitude=latitude,
                longitude=longitude,
                accuracy=accuracy,
                timestamp=timestamp,
                metadata=metadata or {},
            )
    except IntegrityError:
        logger.info(
            "Duplicate %s event suppressed for presence %s at %s",
            event_type,
            presence.pk,
            timestamp,
        )
        return None


def _persist_decision(
    *,
    presence: Presence,
    decision: TransitionDecision,
    evaluation: GeofenceEvaluation,
    payload: LocationPayload,
    location_update: LocationUpdate,
) -> PresenceOutcome:
    """Apply a decision to the row and write the events it produced."""
    previous_status = presence.status

    presence.status = decision.status
    presence.consecutive_inside = decision.consecutive_inside
    presence.consecutive_outside = decision.consecutive_outside
    presence.last_reading_at = payload.recorded_at
    presence.last_seen_at = payload.recorded_at
    presence.last_latitude = payload.latitude
    presence.last_longitude = payload.longitude
    presence.last_accuracy = payload.accuracy
    presence.last_distance_m = evaluation.distance_to_boundary_m
    presence.last_verdict = evaluation.verdict

    if decision.set_check_in:
        presence.check_in_at = payload.recorded_at
    if decision.set_check_out:
        presence.check_out_at = payload.recorded_at
    if decision.status != PresenceStatus.STALE:
        presence.stale_since = None

    presence.save(
        update_fields=[
            "status",
            "consecutive_inside",
            "consecutive_outside",
            "last_reading_at",
            "last_seen_at",
            "last_latitude",
            "last_longitude",
            "last_accuracy",
            "last_distance_m",
            "last_verdict",
            "check_in_at",
            "check_out_at",
            "stale_since",
            "updated_at",
        ]
    )

    emitted: list[str] = []
    for event_type, reason in decision.events:
        event = _write_event(
            presence=presence,
            event_type=event_type,
            reason=reason,
            previous_status=previous_status,
            new_status=decision.status,
            timestamp=payload.recorded_at,
            latitude=payload.latitude,
            longitude=payload.longitude,
            accuracy=payload.accuracy,
            location_update=location_update,
            metadata={
                "verdict": evaluation.verdict,
                "distance_to_boundary_m": round(evaluation.distance_to_boundary_m, 2),
                "accuracy_margin_m": round(evaluation.accuracy_margin_m, 2),
                "confidence": evaluation.confidence,
            },
        )
        if event is not None:
            emitted.append(event_type)

    return PresenceOutcome(
        presence=presence,
        evaluation=evaluation,
        previous_status=previous_status,
        status=decision.status,
        events=emitted,
        applied=decision.applied,
        skip_reason=decision.skip_reason,
    )


def _touch_unapplied(
    *, presence: Presence, evaluation: GeofenceEvaluation, decision: TransitionDecision
) -> PresenceOutcome:
    """Record that a reading was seen but deliberately not applied."""
    return PresenceOutcome(
        presence=presence,
        evaluation=evaluation,
        previous_status=presence.status,
        status=presence.status,
        applied=False,
        skip_reason=decision.skip_reason,
    )


def _get_or_create_presence(
    *, user: User, geofence: Geofence, day, organization_id: int
) -> Presence:
    """Fetch the row for the day, locked, creating it if this is the first entry."""
    presence = (
        Presence.objects.select_for_update()
        .filter(user=user, geofence=geofence, date=day)
        .first()
    )
    if presence is not None:
        return presence

    try:
        with transaction.atomic():
            return Presence.objects.create(
                user=user,
                organization_id=organization_id,
                geofence=geofence,
                date=day,
                status=PresenceStatus.UNKNOWN,
            )
    except IntegrityError:
        # Another transaction created it between the SELECT and the INSERT.
        return (
            Presence.objects.select_for_update()
            .get(user=user, geofence=geofence, date=day)
        )


def _apply_to_presence(
    *,
    user: User,
    organization,
    payload: LocationPayload,
    location_update: LocationUpdate,
) -> tuple[list[GeofenceEvaluation], list[PresenceOutcome]]:
    day = local_date(payload.recorded_at, organization.timezone)

    # Rows that already exist for the day must be evaluated even if their
    # geofence was deactivated in the meantime, otherwise a user could stay
    # PRESENT forever in a retired area.
    existing = {
        presence.geofence_id: presence
        for presence in Presence.objects.select_for_update()
        .filter(user=user, date=day)
        .order_by("geofence_id")
    }

    evaluated = evaluate_point(
        organization_id=organization.pk,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy=payload.accuracy,
        include_geofence_ids=tuple(existing),
    )

    evaluations: list[GeofenceEvaluation] = []
    outcomes: list[PresenceOutcome] = []

    for geofence, evaluation in evaluated:
        evaluations.append(evaluation)
        presence = existing.get(geofence.pk)

        if presence is None:
            if not evaluation.is_inside:
                # Lazy creation: a user who has never been inside this geofence
                # gets no row at all. "No row" is what UNKNOWN means, and it
                # keeps the table proportional to actual attendance.
                continue
            presence = _get_or_create_presence(
                user=user,
                geofence=geofence,
                day=day,
                organization_id=organization.pk,
            )
            existing[geofence.pk] = presence

        context = ReadingContext(
            verdict=evaluation.verdict,
            recorded_at=payload.recorded_at,
            required_inside_readings=evaluation.required_inside_readings,
            required_outside_readings=evaluation.required_outside_readings,
            streak_max_gap_seconds=geo_conf.STREAK_MAX_GAP_SECONDS,
        )
        decision = apply_reading(_presence_state(presence), context)

        if not decision.applied:
            outcomes.append(
                _touch_unapplied(
                    presence=presence, evaluation=evaluation, decision=decision
                )
            )
            continue

        outcomes.append(
            _persist_decision(
                presence=presence,
                decision=decision,
                evaluation=evaluation,
                payload=payload,
                location_update=location_update,
            )
        )

    return evaluations, outcomes


def process_location_update(
    *, user: User, payload: LocationPayload, now: datetime | None = None
) -> LocationIngestResult:
    """Ingest one GPS observation and return the authoritative outcome."""
    if not user.organization_id:
        raise ValidationFailed(
            "Your account is not attached to an organization.",
            errors={"detail": ["Account is not attached to an organization."]},
        )

    organization = user.organization
    now = now or utc_now()

    with transaction.atomic():
        # Serialise everything this user does; released at COMMIT.
        advisory_xact_lock(LOCK_NAMESPACE_LOCATION_PROCESSING, user.pk)

        replay = location_selectors.find_replay(
            user_id=user.pk,
            client_event_id=payload.client_event_id,
            recorded_at=payload.recorded_at,
        )
        if replay is not None:
            logger.info(
                "Idempotent replay of location update %s for user %s", replay.pk, user.pk
            )
            return LocationIngestResult(
                location_update=replay,
                duplicate=True,
                trusted=replay.is_trusted,
                skipped_reason="DUPLICATE",
            )

        previous = location_selectors.last_trusted_update_for_user(user.pk)
        anomalies = location_services.detect_anomalies(
            user_id=user.pk, payload=payload, previous=previous, now=now
        )
        location_update = location_services.store_location_update(
            user=user,
            organization=organization,
            payload=payload,
            anomalies=anomalies,
        )

        if not location_update.is_trusted:
            # Stored for the audit trail, excluded from every presence decision.
            location_services.mark_processed(location_update, at=now)
            return LocationIngestResult(
                location_update=location_update,
                trusted=False,
                anomalies=anomalies,
                skipped_reason="UNTRUSTED_READING",
            )

        evaluations, outcomes = _apply_to_presence(
            user=user,
            organization=organization,
            payload=payload,
            location_update=location_update,
        )
        location_services.mark_processed(location_update, at=now)

    return LocationIngestResult(
        location_update=location_update,
        trusted=True,
        anomalies=anomalies,
        evaluations=evaluations,
        outcomes=outcomes,
    )


__all__ = [
    "LocationIngestResult",
    "PresenceOutcome",
    "process_location_update",
    "PresenceEventType",
]
