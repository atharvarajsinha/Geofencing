"""Write-side operations for geofences.

The client never sends a shape the backend trusts: it sends numbers, and this
module validates them into the float columns the model stores. No geometry
library is involved anywhere in the path.
"""
from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from common.exceptions import Conflict, ValidationFailed
from common.utils.geo import bbox_for_circle
from geofences import validators
from geofences.enums import GeofenceType
from geofences.models import Geofence
from organizations.models import Organization


def _require(value: Any, field: str, message: str) -> Any:
    if value is None:
        raise ValidationFailed(errors={field: [message]})
    return value


#: Names of every payload key that describes a shape.
SHAPE_FIELDS = frozenset(
    {
        "geofence_type",
        "latitude",
        "longitude",
        "radius",
        "min_latitude",
        "max_latitude",
        "min_longitude",
        "max_longitude",
    }
)


def _build_shape_fields(
    *,
    geofence_type: str,
    latitude: float | None,
    longitude: float | None,
    radius: float | None,
    min_latitude: float | None,
    max_latitude: float | None,
    min_longitude: float | None,
    max_longitude: float | None,
) -> dict[str, Any]:
    """Validate the shape payload and return the model fields it maps to.

    A CIRCLE leaves the bounding box to ``Geofence.refresh_bounding_box``,
    which derives it from the centre and radius on save.
    """
    if geofence_type == GeofenceType.CIRCLE:
        _require(latitude, "latitude", "Required for a CIRCLE geofence.")
        _require(longitude, "longitude", "Required for a CIRCLE geofence.")
        _require(radius, "radius", "Required for a CIRCLE geofence.")
        center_latitude, center_longitude = validators.validate_center(latitude, longitude)
        validated_radius = validators.validate_radius(radius)
        (
            box_min_lat,
            box_max_lat,
            box_min_lon,
            box_max_lon,
        ) = bbox_for_circle(center_latitude, center_longitude, validated_radius)
        return {
            "center_latitude": center_latitude,
            "center_longitude": center_longitude,
            "radius": validated_radius,
            "min_latitude": box_min_lat,
            "max_latitude": box_max_lat,
            "min_longitude": box_min_lon,
            "max_longitude": box_max_lon,
        }

    if geofence_type == GeofenceType.RECTANGLE:
        for field, value in (
            ("min_latitude", min_latitude),
            ("max_latitude", max_latitude),
            ("min_longitude", min_longitude),
            ("max_longitude", max_longitude),
        ):
            _require(value, field, "Required for a RECTANGLE geofence.")
        box = validators.validate_bounding_box(
            min_latitude=min_latitude,
            max_latitude=max_latitude,
            min_longitude=min_longitude,
            max_longitude=max_longitude,
        )
        return {
            "center_latitude": None,
            "center_longitude": None,
            "radius": None,
            **box,
        }

    raise ValidationFailed(
        errors={"type": [f"Unsupported geofence type {geofence_type!r}."]}
    )


@transaction.atomic
def create_geofence(
    *,
    organization: Organization,
    name: str,
    geofence_type: str,
    latitude: float | None = None,
    longitude: float | None = None,
    radius: float | None = None,
    min_latitude: float | None = None,
    max_latitude: float | None = None,
    min_longitude: float | None = None,
    max_longitude: float | None = None,
    entry_radius: float | None = None,
    exit_radius: float | None = None,
    required_inside_readings: int | None = None,
    required_outside_readings: int | None = None,
    stale_after_seconds: int | None = None,
    is_active: bool = True,
) -> Geofence:
    shape = _build_shape_fields(
        geofence_type=geofence_type,
        latitude=latitude,
        longitude=longitude,
        radius=radius,
        min_latitude=min_latitude,
        max_latitude=max_latitude,
        min_longitude=min_longitude,
        max_longitude=max_longitude,
    )
    resolved_entry, resolved_exit = validators.validate_hysteresis(
        geofence_type=geofence_type,
        radius=shape.get("radius"),
        entry_radius=entry_radius,
        exit_radius=exit_radius,
    )

    geofence = Geofence(
        organization=organization,
        name=name.strip(),
        geofence_type=geofence_type,
        entry_radius=resolved_entry,
        exit_radius=resolved_exit,
        required_inside_readings=required_inside_readings,
        required_outside_readings=required_outside_readings,
        stale_after_seconds=stale_after_seconds,
        is_active=is_active,
        **shape,
    )
    geofence.full_clean(exclude=["organization"])
    try:
        geofence.save()
    except IntegrityError as exc:  # unique (organization, name)
        raise Conflict(
            "A geofence with this name already exists in your organization.",
            errors={"name": ["This name is already in use."]},
        ) from exc
    return geofence


@transaction.atomic
def update_geofence(*, geofence: Geofence, **payload: Any) -> Geofence:
    """Partially update a geofence, revalidating whatever the change affects."""
    updatable = {
        "name",
        "geofence_type",
        "latitude",
        "longitude",
        "radius",
        "min_latitude",
        "max_latitude",
        "min_longitude",
        "max_longitude",
        "entry_radius",
        "exit_radius",
        "required_inside_readings",
        "required_outside_readings",
        "stale_after_seconds",
        "is_active",
    }
    unknown = set(payload) - updatable
    if unknown:
        raise ValidationFailed(
            errors={key: ["Unknown field."] for key in sorted(unknown)}
        )

    geofence_type = payload.get("geofence_type", geofence.geofence_type)
    shape_touched = bool(SHAPE_FIELDS & set(payload))

    if shape_touched:
        if geofence_type == GeofenceType.CIRCLE:
            # Fall back to the stored centre so a radius-only edit keeps its place.
            latitude = payload.get("latitude", geofence.center_latitude)
            longitude = payload.get("longitude", geofence.center_longitude)
            radius = payload.get("radius", geofence.radius)
            box = {key: None for key in ("min_latitude", "max_latitude", "min_longitude", "max_longitude")}
        else:
            latitude = longitude = radius = None
            # An edit that moves one edge keeps the other three.
            box = {
                key: payload.get(key, getattr(geofence, key))
                for key in ("min_latitude", "max_latitude", "min_longitude", "max_longitude")
            }
        shape = _build_shape_fields(
            geofence_type=geofence_type,
            latitude=latitude,
            longitude=longitude,
            radius=radius,
            **box,
        )
        for field, value in shape.items():
            setattr(geofence, field, value)
        geofence.geofence_type = geofence_type

    # When the shape changes and the admin does not restate the thresholds we
    # recompute them from the new radius: thresholds derived from the previous
    # radius would silently become inconsistent with the drawn area.
    if shape_touched or {"entry_radius", "exit_radius"} & set(payload):
        entry = payload.get(
            "entry_radius", geofence.entry_radius if not shape_touched else None
        )
        exit_ = payload.get(
            "exit_radius", geofence.exit_radius if not shape_touched else None
        )
        geofence.entry_radius, geofence.exit_radius = validators.validate_hysteresis(
            geofence_type=geofence_type,
            radius=geofence.radius,
            entry_radius=entry,
            exit_radius=exit_,
        )

    for field in (
        "name",
        "required_inside_readings",
        "required_outside_readings",
        "stale_after_seconds",
        "is_active",
    ):
        if field in payload:
            setattr(geofence, field, payload[field])

    geofence.full_clean(exclude=["organization"])
    try:
        geofence.save()
    except IntegrityError as exc:
        raise Conflict(
            "A geofence with this name already exists in your organization.",
            errors={"name": ["This name is already in use."]},
        ) from exc
    return geofence


@transaction.atomic
def delete_geofence(*, geofence: Geofence) -> None:
    """Remove a geofence.

    Presence rows keep their historical value: ``Presence.geofence`` and
    ``PresenceEvent.geofence`` are ``PROTECT``ed, so a geofence that has ever
    been used cannot be deleted. Deactivate it instead - that is why
    ``is_active`` exists.
    """
    try:
        geofence.delete()
    except ProtectedError as exc:
        raise Conflict(
            "This geofence has attendance history and cannot be deleted. "
            "Set is_active=false to retire it instead.",
            errors={"detail": ["Geofence has related presence records."]},
        ) from exc
