"""The pure-Python geometry that replaced PostGIS.

These are the only place the project computes distance, so they carry the
correctness of every presence decision. No database, no Django.
"""
from __future__ import annotations

import pytest

from common.utils.geo import (
    METRES_PER_DEGREE_LATITUDE,
    bbox_area_km2,
    bbox_for_circle,
    haversine_distance_m,
    metres_per_degree_longitude,
    point_in_bbox,
    signed_distance_to_bbox_m,
    speed_kmh,
)

CAMPUS_LATITUDE = 29.5976
CAMPUS_LONGITUDE = 79.6591

#: ~200 m x ~200 m box centred on the campus.
BOX = {
    "min_latitude": CAMPUS_LATITUDE - 100 / METRES_PER_DEGREE_LATITUDE,
    "max_latitude": CAMPUS_LATITUDE + 100 / METRES_PER_DEGREE_LATITUDE,
    "min_longitude": CAMPUS_LONGITUDE
    - 100 / metres_per_degree_longitude(CAMPUS_LATITUDE),
    "max_longitude": CAMPUS_LONGITUDE
    + 100 / metres_per_degree_longitude(CAMPUS_LATITUDE),
}


def north(metres: float) -> float:
    return CAMPUS_LATITUDE + metres / METRES_PER_DEGREE_LATITUDE


def east(metres: float) -> float:
    return CAMPUS_LONGITUDE + metres / metres_per_degree_longitude(CAMPUS_LATITUDE)


class TestHaversine:
    def test_zero_distance(self):
        assert haversine_distance_m(29.0, 79.0, 29.0, 79.0) == 0.0

    def test_known_northward_offset(self):
        assert haversine_distance_m(
            CAMPUS_LATITUDE, CAMPUS_LONGITUDE, north(150), CAMPUS_LONGITUDE
        ) == pytest.approx(150, abs=0.1)

    def test_known_eastward_offset(self):
        assert haversine_distance_m(
            CAMPUS_LATITUDE, CAMPUS_LONGITUDE, CAMPUS_LATITUDE, east(150)
        ) == pytest.approx(150, abs=0.5)

    def test_symmetry(self):
        forward = haversine_distance_m(12.9, 77.5, 13.0, 77.6)
        backward = haversine_distance_m(13.0, 77.6, 12.9, 77.5)
        assert forward == pytest.approx(backward)

    def test_a_degree_of_latitude_is_about_111_km(self):
        assert haversine_distance_m(0.0, 0.0, 1.0, 0.0) == pytest.approx(
            111_195, abs=50
        )


class TestMetresPerDegreeLongitude:
    def test_widest_at_the_equator(self):
        assert metres_per_degree_longitude(0.0) == pytest.approx(
            METRES_PER_DEGREE_LATITUDE
        )

    def test_shrinks_towards_the_pole(self):
        assert metres_per_degree_longitude(60.0) == pytest.approx(
            METRES_PER_DEGREE_LATITUDE / 2, rel=1e-3
        )

    def test_vanishes_at_the_pole(self):
        assert metres_per_degree_longitude(90.0) == pytest.approx(0.0, abs=1e-6)


class TestSignedDistanceToBbox:
    def test_centre_is_negative_by_the_half_width(self):
        distance = signed_distance_to_bbox_m(CAMPUS_LATITUDE, CAMPUS_LONGITUDE, **BOX)
        assert distance == pytest.approx(-100, abs=1)

    def test_on_the_edge_is_zero(self):
        assert signed_distance_to_bbox_m(
            BOX["min_latitude"], CAMPUS_LONGITUDE, **BOX
        ) == pytest.approx(0.0, abs=0.01)
        assert signed_distance_to_bbox_m(
            CAMPUS_LATITUDE, BOX["max_longitude"], **BOX
        ) == pytest.approx(0.0, abs=0.01)

    def test_inside_reports_distance_to_the_nearest_edge(self):
        # 5 m inside the southern edge, but ~100 m from east and west.
        latitude = BOX["min_latitude"] + 5 / METRES_PER_DEGREE_LATITUDE
        assert signed_distance_to_bbox_m(
            latitude, CAMPUS_LONGITUDE, **BOX
        ) == pytest.approx(-5, abs=0.1)

    @pytest.mark.parametrize("metres", [50, 100, 500])
    def test_due_north_of_the_box(self, metres):
        latitude = BOX["max_latitude"] + metres / METRES_PER_DEGREE_LATITUDE
        assert signed_distance_to_bbox_m(
            latitude, CAMPUS_LONGITUDE, **BOX
        ) == pytest.approx(metres, abs=0.1)

    @pytest.mark.parametrize("metres", [50, 100, 500])
    def test_due_west_of_the_box(self, metres):
        longitude = BOX["min_longitude"] - metres / metres_per_degree_longitude(
            CAMPUS_LATITUDE
        )
        assert signed_distance_to_bbox_m(
            CAMPUS_LATITUDE, longitude, **BOX
        ) == pytest.approx(metres, abs=0.5)

    def test_diagonally_outside_measures_to_the_corner(self):
        latitude = BOX["max_latitude"] + 100 / METRES_PER_DEGREE_LATITUDE
        longitude = BOX["max_longitude"] + 100 / metres_per_degree_longitude(
            CAMPUS_LATITUDE
        )
        # Pythagoras, not the sum of the two offsets.
        assert signed_distance_to_bbox_m(latitude, longitude, **BOX) == pytest.approx(
            141.42, abs=1
        )

    def test_sign_flips_exactly_at_the_boundary(self):
        epsilon = 0.01 / METRES_PER_DEGREE_LATITUDE
        just_inside = signed_distance_to_bbox_m(
            BOX["min_latitude"] + epsilon, CAMPUS_LONGITUDE, **BOX
        )
        just_outside = signed_distance_to_bbox_m(
            BOX["min_latitude"] - epsilon, CAMPUS_LONGITUDE, **BOX
        )
        assert just_inside < 0 < just_outside

    def test_longitude_scale_uses_an_in_box_latitude(self):
        """A point far north of an equatorial box must not use its own cosine.

        Scaling by the point's latitude would understate the east/west distance
        and could report a point outside the box as inside it.
        """
        equator_box = {
            "min_latitude": -1.0,
            "max_latitude": 1.0,
            "min_longitude": -1.0,
            "max_longitude": 1.0,
        }
        # 60 degrees north, 2 degrees east of the box's eastern edge.
        distance = signed_distance_to_bbox_m(60.0, 3.0, **equator_box)
        assert distance > 0
        # The dominant term is the ~59 degrees of latitude, not the longitude.
        assert distance == pytest.approx(
            59.0 * METRES_PER_DEGREE_LATITUDE, rel=0.05
        )


class TestPointInBbox:
    def test_inside(self):
        assert point_in_bbox(CAMPUS_LATITUDE, CAMPUS_LONGITUDE, **BOX)

    def test_outside(self):
        assert not point_in_bbox(0.0, 0.0, **BOX)

    def test_edges_are_inclusive(self):
        assert point_in_bbox(BOX["min_latitude"], BOX["min_longitude"], **BOX)
        assert point_in_bbox(BOX["max_latitude"], BOX["max_longitude"], **BOX)


class TestBboxForCircle:
    @pytest.mark.parametrize("radius", [10.0, 150.0, 5_000.0])
    def test_envelope_matches_the_radius(self, radius):
        min_lat, max_lat, min_lon, max_lon = bbox_for_circle(
            CAMPUS_LATITUDE, CAMPUS_LONGITUDE, radius
        )
        half_height = (max_lat - min_lat) / 2 * METRES_PER_DEGREE_LATITUDE
        assert half_height == pytest.approx(radius, rel=1e-6)

    def test_envelope_contains_the_whole_circle(self):
        """Every point on the circle must fall inside the stored box.

        This is what makes the box safe to use as a query prefilter.
        """
        from math import cos, radians, sin

        radius = 500.0
        min_lat, max_lat, min_lon, max_lon = bbox_for_circle(
            CAMPUS_LATITUDE, CAMPUS_LONGITUDE, radius
        )
        for degrees in range(0, 360, 5):
            bearing = radians(degrees)
            latitude = CAMPUS_LATITUDE + (
                radius * cos(bearing) / METRES_PER_DEGREE_LATITUDE
            )
            longitude = CAMPUS_LONGITUDE + (
                radius * sin(bearing) / metres_per_degree_longitude(CAMPUS_LATITUDE)
            )
            assert min_lat - 1e-9 <= latitude <= max_lat + 1e-9
            assert min_lon - 1e-9 <= longitude <= max_lon + 1e-9

    def test_latitude_is_clamped_at_the_poles(self):
        min_lat, max_lat, _, _ = bbox_for_circle(89.999, 0.0, 50_000.0)
        assert max_lat <= 90.0
        assert min_lat >= -90.0


class TestBboxArea:
    def test_two_hundred_metre_square(self):
        assert bbox_area_km2(**BOX) == pytest.approx(0.04, rel=0.02)

    def test_degenerate_box_has_no_area(self):
        assert (
            bbox_area_km2(
                min_latitude=10.0,
                max_latitude=10.0,
                min_longitude=20.0,
                max_longitude=21.0,
            )
            == 0.0
        )


class TestSpeed:
    def test_typical_speed(self):
        assert speed_kmh(1000.0, 60.0) == pytest.approx(60.0)

    def test_zero_elapsed_time_is_not_infinite(self):
        assert speed_kmh(1000.0, 0.0) == 0.0

    def test_negative_elapsed_time_is_not_negative_speed(self):
        assert speed_kmh(1000.0, -5.0) == 0.0
