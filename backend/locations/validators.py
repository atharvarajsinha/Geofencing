"""Validation of an incoming GPS observation.

Pure functions over the payload plus configuration: no database access, no
writes. The result is a frozen :class:`LocationPayload` that the service layer
can trust.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.utils import timezone

from common.conf import geo_conf
from common.exceptions import ValidationFailed
from common.utils.time import utc_now
from geofences.validators import (
    validate_accuracy,
    validate_latitude,
    validate_longitude,
)

MAX_IDENTIFIER_LENGTH = 64

#: Fields a client must never send: the backend owns presence.
CLIENT_FORBIDDEN_FIELDS = frozenset(
    {"status", "presence_status", "is_present", "distance", "inside"}
)


def reject_client_supplied_status(data: Any) -> None:
    """Refuse payloads that try to assert presence.

    Silently dropping these fields would let a frontend author believe the
    backend honours them. The backend is authoritative, so say so loudly.
    """
    if not isinstance(data, dict):
        return
    supplied = sorted(CLIENT_FORBIDDEN_FIELDS & set(data))
    if supplied:
        raise ValidationFailed(
            errors={
                field: [
                    "Presence is computed by the backend and must not be supplied "
                    "by the client."
                ]
                for field in supplied
            }
        )


@dataclass(frozen=True)
class LocationPayload:
    """A validated GPS observation, ready to be persisted."""

    latitude: float
    longitude: float
    accuracy: float
    recorded_at: datetime
    speed: float | None = None
    heading: float | None = None
    altitude: float | None = None
    device_id: str = ""
    session_id: str = ""
    client_event_id: str | None = None

    @property
    def age_seconds(self) -> float:
        return (utc_now() - self.recorded_at).total_seconds()


def _validate_identifier(value: Any, field: str) -> str:
    if value in (None, ""):
        return ""
    text = str(value).strip()
    if len(text) > MAX_IDENTIFIER_LENGTH:
        raise ValidationFailed(
            errors={field: [f"Must not exceed {MAX_IDENTIFIER_LENGTH} characters."]}
        )
    return text


def validate_recorded_at(recorded_at: Any, *, now: datetime | None = None) -> datetime:
    """Reject clock-skewed and obviously stale fixes.

    Two different limits apply:

    * ``MAX_CLOCK_SKEW_SECONDS`` - a fix from the future is either a broken
      device clock or a forged payload,
    * ``MAX_LOCATION_AGE_SECONDS`` - an old fix is accepted (a PWA coming back
      online legitimately flushes its queue) but only up to a point, because
      replaying yesterday's coordinates must never revive yesterday's presence.
    """
    if recorded_at is None:
        raise ValidationFailed(errors={"recorded_at": ["This field is required."]})
    if not isinstance(recorded_at, datetime):
        raise ValidationFailed(
            errors={"recorded_at": ["Expected an ISO 8601 datetime with timezone."]}
        )
    if timezone.is_naive(recorded_at):
        raise ValidationFailed(
            errors={
                "recorded_at": [
                    "Timestamp must include a timezone offset (use UTC, e.g. "
                    "2026-08-26T12:20:15Z)."
                ]
            }
        )

    now = now or utc_now()
    skew = (recorded_at - now).total_seconds()
    if skew > geo_conf.MAX_CLOCK_SKEW_SECONDS:
        raise ValidationFailed(
            errors={
                "recorded_at": [
                    f"Timestamp is {skew:.0f}s in the future; the maximum accepted "
                    f"clock skew is {geo_conf.MAX_CLOCK_SKEW_SECONDS}s."
                ]
            }
        )
    age = -skew
    if age > geo_conf.MAX_LOCATION_AGE_SECONDS:
        raise ValidationFailed(
            errors={
                "recorded_at": [
                    f"Fix is {age:.0f}s old; the maximum accepted age is "
                    f"{geo_conf.MAX_LOCATION_AGE_SECONDS}s."
                ]
            }
        )
    return recorded_at


def _validate_speed(speed: Any) -> float | None:
    if speed is None:
        return None
    try:
        value = float(speed)
    except (TypeError, ValueError):
        raise ValidationFailed(errors={"speed": ["A valid number is required."]})
    if value < 0:
        raise ValidationFailed(errors={"speed": ["Speed must not be negative."]})
    return value


def _validate_heading(heading: Any) -> float | None:
    if heading is None:
        return None
    try:
        value = float(heading)
    except (TypeError, ValueError):
        raise ValidationFailed(errors={"heading": ["A valid number is required."]})
    if not 0.0 <= value <= 360.0:
        raise ValidationFailed(errors={"heading": ["Heading must be between 0 and 360."]})
    return value


def _validate_altitude(altitude: Any) -> float | None:
    if altitude is None:
        return None
    try:
        value = float(altitude)
    except (TypeError, ValueError):
        raise ValidationFailed(errors={"altitude": ["A valid number is required."]})
    if not -500.0 <= value <= 20_000.0:
        raise ValidationFailed(
            errors={"altitude": ["Altitude must be between -500 and 20000 metres."]}
        )
    return value


def validate_location_payload(
    data: dict[str, Any], *, now: datetime | None = None
) -> LocationPayload:
    """Validate a location update payload end to end."""
    reject_client_supplied_status(data)

    return LocationPayload(
        latitude=validate_latitude(data.get("latitude")),
        longitude=validate_longitude(data.get("longitude")),
        accuracy=validate_accuracy(data.get("accuracy")),
        recorded_at=validate_recorded_at(data.get("recorded_at"), now=now),
        speed=_validate_speed(data.get("speed")),
        heading=_validate_heading(data.get("heading")),
        altitude=_validate_altitude(data.get("altitude")),
        device_id=_validate_identifier(data.get("device_id"), "device_id"),
        session_id=_validate_identifier(data.get("session_id"), "session_id"),
        client_event_id=_validate_identifier(
            data.get("client_event_id"), "client_event_id"
        )
        or None,
    )
