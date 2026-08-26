"""Pure-python geographic helpers.

This project deliberately has **no GeoDjango / PostGIS / GDAL dependency**.
Every geographic decision is made here, in Python, against a spherical Earth
model. That costs a little accuracy compared to PostGIS geodesics (well under a
metre at the scale of a building or a campus, which is the scale geofencing
operates at) and buys a plain ``psycopg`` install with no native libraries.

Two shapes are supported, and both reduce to a *signed distance in metres* from
the shape's boundary - negative inside, positive outside:

* ``CIRCLE``    - :func:`haversine_distance_m` to the centre, minus the radius,
* ``RECTANGLE`` - :func:`signed_distance_to_bbox_m`.

Keeping one signed axis for both shapes is what lets the presence state machine
stay ignorant of geometry entirely.
"""
from __future__ import annotations

from math import asin, cos, hypot, radians, sin, sqrt

#: Mean Earth radius (metres). IUGG mean radius, the same sphere PostGIS
#: ``ST_DistanceSphere`` uses, so historical values stay comparable.
EARTH_RADIUS_M = 6_371_008.8

#: Metres per degree of latitude on that sphere (constant everywhere).
METRES_PER_DEGREE_LATITUDE = EARTH_RADIUS_M * radians(1.0)

MIN_LATITUDE = -90.0
MAX_LATITUDE = 90.0
MIN_LONGITUDE = -180.0
MAX_LONGITUDE = 180.0


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS84 coordinates."""
    phi1, phi2 = radians(lat1), radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = radians(lon2 - lon1)
    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))


def metres_per_degree_longitude(latitude: float) -> float:
    """Metres in one degree of longitude at ``latitude``.

    Converges to zero at the poles, which is why the callers below clamp the
    reference latitude into the box rather than using the point's own latitude.
    """
    return METRES_PER_DEGREE_LATITUDE * cos(radians(latitude))


def signed_distance_to_bbox_m(
    latitude: float,
    longitude: float,
    *,
    min_latitude: float,
    max_latitude: float,
    min_longitude: float,
    max_longitude: float,
) -> float:
    """Signed distance in metres from a point to a lat/lon rectangle.

    Negative when the point is inside (magnitude = distance to the *nearest*
    edge), positive when outside (magnitude = distance to the box), so the
    result sits on the same axis as ``distance - radius`` does for a circle.

    The local equirectangular approximation used here is exact in latitude and
    accurate in longitude to the extent that ``cos(latitude)`` is constant
    across the box - a fraction of a percent for any realistic site.
    """
    # Latitude offsets: positive means "outside the box on that side".
    south_of = (min_latitude - latitude) * METRES_PER_DEGREE_LATITUDE
    north_of = (latitude - max_latitude) * METRES_PER_DEGREE_LATITUDE
    dy = max(south_of, north_of)

    # Scale longitude at the in-box latitude closest to the point: using the
    # point's own latitude would understate east/west distance for a point far
    # north of a box straddling the equator.
    reference_latitude = min(max(latitude, min_latitude), max_latitude)
    scale = metres_per_degree_longitude(reference_latitude)
    west_of = (min_longitude - longitude) * scale
    east_of = (longitude - max_longitude) * scale
    dx = max(west_of, east_of)

    if dx > 0.0 and dy > 0.0:
        # Diagonally outside: the nearest point of the box is a corner.
        return hypot(dx, dy)
    # Inside (both <= 0, max is the least negative = -distance to nearest edge)
    # or outside along exactly one axis (max is that positive offset).
    return max(dx, dy)


def point_in_bbox(
    latitude: float,
    longitude: float,
    *,
    min_latitude: float,
    max_latitude: float,
    min_longitude: float,
    max_longitude: float,
) -> bool:
    """Plain containment, ignoring GPS accuracy and hysteresis."""
    return (
        min_latitude <= latitude <= max_latitude
        and min_longitude <= longitude <= max_longitude
    )


def bbox_for_circle(
    latitude: float, longitude: float, radius_m: float
) -> tuple[float, float, float, float]:
    """Bounding box ``(min_lat, max_lat, min_lon, max_lon)`` enclosing a circle.

    Stored alongside every circle so the database can prefilter candidates with
    an ordinary B-tree index instead of a spatial one. Latitude is clamped to
    the poles; longitude is clamped rather than wrapped, because a geofence that
    spans the antimeridian is rejected at validation time.
    """
    lat_delta = radius_m / METRES_PER_DEGREE_LATITUDE
    min_lat = max(latitude - lat_delta, MIN_LATITUDE)
    max_lat = min(latitude + lat_delta, MAX_LATITUDE)

    # A degree of longitude is *shortest* at the latitude furthest from the
    # equator, so that latitude yields the *widest* span in degrees. Using the
    # poleward edge over-approximates slightly, which is the safe direction:
    # an envelope must never be narrower than the circle it encloses, or the
    # query prefilter would drop a geofence the exact test would have accepted.
    poleward_latitude = max(abs(min_lat), abs(max_lat))
    scale = metres_per_degree_longitude(poleward_latitude)
    lon_delta = 180.0 if scale <= 0.0 else radius_m / scale

    return (
        min_lat,
        max_lat,
        max(longitude - lon_delta, MIN_LONGITUDE),
        min(longitude + lon_delta, MAX_LONGITUDE),
    )


def bbox_area_km2(
    *,
    min_latitude: float,
    max_latitude: float,
    min_longitude: float,
    max_longitude: float,
) -> float:
    """Approximate rectangle area in km2, for sanity-checking admin input."""
    height_m = (max_latitude - min_latitude) * METRES_PER_DEGREE_LATITUDE
    mid_latitude = (min_latitude + max_latitude) / 2.0
    width_m = (max_longitude - min_longitude) * metres_per_degree_longitude(mid_latitude)
    return max(height_m, 0.0) * max(width_m, 0.0) / 1_000_000.0


def latitude_in_range(latitude: float) -> bool:
    return MIN_LATITUDE <= latitude <= MAX_LATITUDE


def longitude_in_range(longitude: float) -> bool:
    return MIN_LONGITUDE <= longitude <= MAX_LONGITUDE


def speed_kmh(distance_m: float, seconds: float) -> float:
    """Average speed in km/h; ``0`` when the time delta is not usable."""
    if seconds <= 0:
        return 0.0
    return (distance_m / seconds) * 3.6
