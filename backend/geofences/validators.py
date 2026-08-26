"""Geofence input validation.

Validators translate untrusted client input into verified shape values. They
never touch the database and never import a geometry library: everything here
is a pure function of the payload plus configuration, which makes the rules
easy to unit test and keeps the project free of GEOS/GDAL.
"""
from __future__ import annotations

from typing import Any

from common.conf import geo_conf
from common.exceptions import ValidationFailed
from common.utils.geo import (
    METRES_PER_DEGREE_LATITUDE,
    bbox_area_km2,
    latitude_in_range,
    longitude_in_range,
    metres_per_degree_longitude,
)


def validate_latitude(latitude: Any, field: str = "latitude") -> float:
    try:
        value = float(latitude)
    except (TypeError, ValueError):
        raise ValidationFailed(errors={field: ["A valid number is required."]})
    if not latitude_in_range(value):
        raise ValidationFailed(errors={field: ["Latitude must be between -90 and 90."]})
    return value


def validate_longitude(longitude: Any, field: str = "longitude") -> float:
    try:
        value = float(longitude)
    except (TypeError, ValueError):
        raise ValidationFailed(errors={field: ["A valid number is required."]})
    if not longitude_in_range(value):
        raise ValidationFailed(
            errors={field: ["Longitude must be between -180 and 180."]}
        )
    return value


def validate_radius(radius: Any, field: str = "radius") -> float:
    try:
        value = float(radius)
    except (TypeError, ValueError):
        raise ValidationFailed(errors={field: ["A valid number is required."]})
    if value < geo_conf.MIN_RADIUS_M:
        raise ValidationFailed(
            errors={field: [f"Radius must be at least {geo_conf.MIN_RADIUS_M:g} metres."]}
        )
    if value > geo_conf.MAX_RADIUS_M:
        raise ValidationFailed(
            errors={field: [f"Radius must not exceed {geo_conf.MAX_RADIUS_M:g} metres."]}
        )
    return value


def validate_center(latitude: Any, longitude: Any) -> tuple[float, float]:
    """Validated circle centre as a ``(latitude, longitude)`` pair."""
    return (
        validate_latitude(latitude, field="latitude"),
        validate_longitude(longitude, field="longitude"),
    )


#: Smallest edge length a rectangle may have. Below this the hysteresis band
#: would swallow the whole shape and every verdict would be UNCERTAIN.
MIN_RECTANGLE_EDGE_M = 1.0


def validate_bounding_box(
    *,
    min_latitude: Any,
    max_latitude: Any,
    min_longitude: Any,
    max_longitude: Any,
) -> dict[str, float]:
    """Validate the four numbers that define a RECTANGLE geofence.

    Returns them as a dict ready to splat onto the model. Ordering is enforced
    rather than silently corrected: a swapped pair almost always means the
    caller mixed up latitude and longitude, and quietly "fixing" it would place
    the geofence somewhere the admin never drew.
    """
    south = validate_latitude(min_latitude, field="min_latitude")
    north = validate_latitude(max_latitude, field="max_latitude")
    west = validate_longitude(min_longitude, field="min_longitude")
    east = validate_longitude(max_longitude, field="max_longitude")

    if north <= south:
        raise ValidationFailed(
            errors={
                "max_latitude": [
                    "max_latitude must be greater than min_latitude."
                ]
            }
        )
    # A box spanning the antimeridian would need wrap-around handling in every
    # comparison. Rejecting it keeps the distance maths a single subtraction.
    if east <= west:
        raise ValidationFailed(
            errors={
                "max_longitude": [
                    "max_longitude must be greater than min_longitude. Geofences "
                    "spanning the 180th meridian are not supported."
                ]
            }
        )

    height_m = (north - south) * METRES_PER_DEGREE_LATITUDE
    width_m = (east - west) * metres_per_degree_longitude((north + south) / 2.0)

    if height_m < MIN_RECTANGLE_EDGE_M or width_m < MIN_RECTANGLE_EDGE_M:
        raise ValidationFailed(
            errors={
                "detail": [
                    f"The rectangle is too small: each edge must be at least "
                    f"{MIN_RECTANGLE_EDGE_M:g} m "
                    f"(got {height_m:.2f} m x {width_m:.2f} m)."
                ]
            }
        )

    area_km2 = bbox_area_km2(
        min_latitude=south,
        max_latitude=north,
        min_longitude=west,
        max_longitude=east,
    )
    if area_km2 > geo_conf.MAX_GEOFENCE_AREA_KM2:
        raise ValidationFailed(
            errors={
                "detail": [
                    f"Rectangle area ({area_km2:.1f} km2) exceeds the maximum of "
                    f"{geo_conf.MAX_GEOFENCE_AREA_KM2:g} km2."
                ]
            }
        )

    return {
        "min_latitude": south,
        "max_latitude": north,
        "min_longitude": west,
        "max_longitude": east,
    }


def bounding_box_from_corners(corners: Any) -> dict[str, float]:
    """Derive a bounding box from a list of ``[longitude, latitude]`` pairs.

    Kept so that a client which already has a drawn outline (or a caller
    migrating old polygon data) can hand it over without computing the extent
    itself. The axis order is GeoJSON's, because that is what mapping libraries
    produce; latitude/longitude confusion is the most common integration bug in
    geofencing, so every pair is range-checked.
    """
    if not isinstance(corners, (list, tuple)) or len(corners) < 2:
        raise ValidationFailed(
            errors={
                "coordinates": [
                    "Expected at least two [longitude, latitude] pairs."
                ]
            }
        )

    latitudes: list[float] = []
    longitudes: list[float] = []
    for index, pair in enumerate(corners):
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValidationFailed(
                errors={
                    "coordinates": [
                        f"Vertex {index} must be a [longitude, latitude] pair."
                    ]
                }
            )
        longitudes.append(validate_longitude(pair[0], field="coordinates"))
        latitudes.append(validate_latitude(pair[1], field="coordinates"))

    return validate_bounding_box(
        min_latitude=min(latitudes),
        max_latitude=max(latitudes),
        min_longitude=min(longitudes),
        max_longitude=max(longitudes),
    )


def validate_hysteresis(
    *,
    geofence_type: str,
    radius: float | None,
    entry_radius: float | None,
    exit_radius: float | None,
) -> tuple[float, float]:
    """Resolve and validate the entry/exit thresholds.

    Returns the pair actually stored on the model. Defaults are derived from
    the nominal radius (circle) or from the configured buffer (rectangle) so an
    admin can create a geofence without knowing what hysteresis is.
    """
    from geofences.enums import GeofenceType

    if geofence_type == GeofenceType.CIRCLE:
        nominal = float(radius or 0.0)
        resolved_entry = (
            float(entry_radius)
            if entry_radius is not None
            else max(nominal - geo_conf.DEFAULT_ENTRY_BUFFER_M, geo_conf.MIN_RADIUS_M)
        )
        resolved_exit = (
            float(exit_radius)
            if exit_radius is not None
            else nominal + geo_conf.DEFAULT_EXIT_BUFFER_M
        )
        if resolved_entry <= 0:
            raise ValidationFailed(
                errors={"entry_radius": ["Entry radius must be greater than zero."]}
            )
    else:
        resolved_entry = (
            float(entry_radius)
            if entry_radius is not None
            else geo_conf.DEFAULT_ENTRY_BUFFER_M
        )
        resolved_exit = (
            float(exit_radius)
            if exit_radius is not None
            else geo_conf.DEFAULT_EXIT_BUFFER_M
        )
        if resolved_entry < 0:
            raise ValidationFailed(
                errors={"entry_radius": ["Entry inset must not be negative."]}
            )

    if resolved_exit <= resolved_entry:
        raise ValidationFailed(
            errors={
                "exit_radius": [
                    "exit_radius must be greater than entry_radius so that the "
                    "hysteresis band is non-empty."
                ]
            }
        )
    if resolved_exit > geo_conf.MAX_RADIUS_M * 2:
        raise ValidationFailed(
            errors={"exit_radius": ["exit_radius is unreasonably large."]}
        )
    return resolved_entry, resolved_exit


def validate_accuracy(accuracy: Any, field: str = "accuracy") -> float:
    """Accuracy must be a non-negative number within a sane upper bound."""
    try:
        value = float(accuracy)
    except (TypeError, ValueError):
        raise ValidationFailed(errors={field: ["A valid number is required."]})
    if value < 0:
        raise ValidationFailed(errors={field: ["Accuracy must not be negative."]})
    if value > geo_conf.HARD_REJECT_ACCURACY_M:
        raise ValidationFailed(
            errors={
                field: [
                    f"Reported accuracy of {value:.0f} m is unusable; the maximum "
                    f"accepted value is {geo_conf.HARD_REJECT_ACCURACY_M:g} m."
                ]
            }
        )
    return value
