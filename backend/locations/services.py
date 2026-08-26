"""Location ingest services: persistence and anomaly detection.

What this module deliberately does *not* claim: browser geolocation cannot be
made spoof-proof. A determined user can feed the Geolocation API arbitrary
coordinates from developer tools or a patched browser. The detectors below
therefore aim at *plausibility*, producing evidence for a human review rather
than automated punishment. Only the two physically impossible patterns
(teleporting and impossible speed) actually exclude a reading from presence
decisions; nothing here bans anybody.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from django.db import transaction

from accounts.models import User
from common.conf import geo_conf
from common.utils.geo import haversine_distance_m, speed_kmh
from common.utils.time import utc_now
from geofences.evaluation import reading_confidence
from locations import selectors
from locations.enums import AnomalySeverity, AnomalyType
from locations.models import LocationAnomaly, LocationUpdate
from locations.validators import LocationPayload
from organizations.models import Organization

logger = logging.getLogger("geofencing.locations")


@dataclass(frozen=True)
class DetectedAnomaly:
    anomaly_type: str
    severity: str
    details: dict[str, Any] = field(default_factory=dict)


def _effective_distance_m(
    payload: LocationPayload, previous: LocationUpdate
) -> tuple[float, float]:
    """Distance between two fixes, and the part of it that exceeds GPS noise.

    Subtracting the two accuracy radii before judging movement is what keeps a
    stationary device with jittery fixes from being reported as travelling at
    100 km/h.
    """
    raw = haversine_distance_m(
        previous.latitude, previous.longitude, payload.latitude, payload.longitude
    )
    noise = float(previous.accuracy or 0.0) + float(payload.accuracy or 0.0)
    return raw, max(raw - noise, 0.0)


def detect_anomalies(
    *,
    user_id: int,
    payload: LocationPayload,
    previous: LocationUpdate | None,
    now: datetime | None = None,
) -> list[DetectedAnomaly]:
    """Inspect one observation in the context of the user's recent history."""
    now = now or utc_now()
    anomalies: list[DetectedAnomaly] = []

    # -- Clock ----------------------------------------------------------
    skew_seconds = (payload.recorded_at - now).total_seconds()
    if skew_seconds > 0:
        anomalies.append(
            DetectedAnomaly(
                anomaly_type=AnomalyType.FUTURE_TIMESTAMP,
                severity=AnomalySeverity.LOW,
                details={"skew_seconds": round(skew_seconds, 3)},
            )
        )

    age_seconds = -skew_seconds
    if age_seconds > geo_conf.STALE_AFTER_SECONDS:
        anomalies.append(
            DetectedAnomaly(
                anomaly_type=AnomalyType.STALE_READING,
                severity=AnomalySeverity.LOW,
                details={
                    "age_seconds": round(age_seconds, 3),
                    "note": "Delayed delivery, typically an offline PWA flushing its queue.",
                },
            )
        )

    # -- Accuracy -------------------------------------------------------
    if payload.accuracy > geo_conf.MAX_ACCEPTABLE_ACCURACY_M:
        severity = (
            AnomalySeverity.MEDIUM
            if payload.accuracy > geo_conf.MAX_ACCEPTABLE_ACCURACY_M * 4
            else AnomalySeverity.LOW
        )
        anomalies.append(
            DetectedAnomaly(
                anomaly_type=AnomalyType.POOR_ACCURACY,
                severity=severity,
                details={
                    "accuracy_m": payload.accuracy,
                    "threshold_m": geo_conf.MAX_ACCEPTABLE_ACCURACY_M,
                },
            )
        )

    # -- Movement -------------------------------------------------------
    if previous is not None:
        elapsed = (payload.recorded_at - previous.recorded_at).total_seconds()
        raw_distance, effective_distance = _effective_distance_m(payload, previous)

        if elapsed >= 1.0:
            implied_speed = speed_kmh(effective_distance, elapsed)
            if implied_speed > geo_conf.MAX_PLAUSIBLE_SPEED_KMH:
                anomalies.append(
                    DetectedAnomaly(
                        anomaly_type=AnomalyType.IMPOSSIBLE_SPEED,
                        severity=AnomalySeverity.HIGH,
                        details={
                            "implied_speed_kmh": round(implied_speed, 2),
                            "max_plausible_kmh": geo_conf.MAX_PLAUSIBLE_SPEED_KMH,
                            "distance_m": round(raw_distance, 2),
                            "effective_distance_m": round(effective_distance, 2),
                            "elapsed_seconds": round(elapsed, 3),
                            "previous_location_update_id": previous.pk,
                        },
                    )
                )

        if (
            effective_distance > geo_conf.JUMP_DISTANCE_M
            and 0 <= elapsed <= geo_conf.JUMP_WINDOW_SECONDS
        ):
            anomalies.append(
                DetectedAnomaly(
                    anomaly_type=AnomalyType.COORDINATE_JUMP,
                    severity=AnomalySeverity.HIGH,
                    details={
                        "distance_m": round(raw_distance, 2),
                        "elapsed_seconds": round(elapsed, 3),
                        "window_seconds": geo_conf.JUMP_WINDOW_SECONDS,
                        "previous_location_update_id": previous.pk,
                    },
                )
            )

    # -- Frequency ------------------------------------------------------
    recent_count = selectors.count_recent_updates(user_id, seconds=60, now=now)
    if recent_count > geo_conf.MAX_UPDATES_PER_MINUTE:
        anomalies.append(
            DetectedAnomaly(
                anomaly_type=AnomalyType.HIGH_FREQUENCY,
                severity=AnomalySeverity.LOW,
                details={
                    "updates_last_minute": recent_count,
                    "max_expected": geo_conf.MAX_UPDATES_PER_MINUTE,
                },
            )
        )

    # -- Frozen coordinates ---------------------------------------------
    identical = selectors.recent_identical_reading_count(
        user_id=user_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        since=now - timedelta(seconds=geo_conf.STATIONARY_MIN_SECONDS),
        tolerance=geo_conf.STATIONARY_TOLERANCE_M,
    )
    if identical >= geo_conf.STATIONARY_MIN_READINGS:
        anomalies.append(
            DetectedAnomaly(
                anomaly_type=AnomalyType.STATIONARY_REPEAT,
                severity=AnomalySeverity.MEDIUM,
                details={
                    "identical_readings": identical,
                    "window_seconds": geo_conf.STATIONARY_MIN_SECONDS,
                    "tolerance_m": geo_conf.STATIONARY_TOLERANCE_M,
                    "note": (
                        "Real GPS jitters; byte-identical coordinates over a long "
                        "window suggest a replayed or synthetic position."
                    ),
                },
            )
        )

    return anomalies


def has_blocking_anomaly(anomalies: list[DetectedAnomaly]) -> bool:
    """HIGH severity means the reading is physically implausible."""
    return any(item.severity == AnomalySeverity.HIGH for item in anomalies)


@transaction.atomic
def store_location_update(
    *,
    user: User,
    organization: Organization,
    payload: LocationPayload,
    anomalies: list[DetectedAnomaly],
) -> LocationUpdate:
    """Persist the fix together with its anomalies."""
    trusted = not has_blocking_anomaly(anomalies)

    location_update = LocationUpdate(
        user=user,
        organization=organization,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy=payload.accuracy,
        speed=payload.speed,
        heading=payload.heading,
        altitude=payload.altitude,
        recorded_at=payload.recorded_at,
        device_id=payload.device_id,
        session_id=payload.session_id,
        client_event_id=payload.client_event_id,
        confidence=reading_confidence(payload.accuracy),
        is_trusted=trusted,
        is_flagged=bool(anomalies),
    )
    location_update.save()

    if anomalies:
        LocationAnomaly.objects.bulk_create(
            [
                LocationAnomaly(
                    user=user,
                    organization=organization,
                    location_update=location_update,
                    anomaly_type=item.anomaly_type,
                    severity=item.severity,
                    details=item.details,
                )
                for item in anomalies
            ]
        )
        if not trusted:
            logger.warning(
                "Untrusted location update %s for user %s: %s",
                location_update.pk,
                user.pk,
                [item.anomaly_type for item in anomalies],
            )

    return location_update


def mark_processed(location_update: LocationUpdate, *, at: datetime | None = None) -> None:
    location_update.processed_at = at or utc_now()
    location_update.save(update_fields=["processed_at"])
