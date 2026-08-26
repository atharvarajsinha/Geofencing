"""Validation of admin supplied geofence shapes.

Nothing here needs a geometry library: a shape is a centre plus a radius, or
four bounding edges.
"""
from __future__ import annotations

import pytest

from common.exceptions import ValidationFailed
from common.utils.geo import METRES_PER_DEGREE_LATITUDE, metres_per_degree_longitude
from geofences import services, validators
from geofences.enums import GeofenceType
from tests.factories import CAMPUS_LATITUDE, CAMPUS_LONGITUDE, campus_bbox

#: A ~200 m x ~130 m box around the campus.
SQUARE_BOX = {
    "min_latitude": 29.5971,
    "max_latitude": 29.5983,
    "min_longitude": 79.6581,
    "max_longitude": 79.6601,
}

#: The same box expressed as GeoJSON [longitude, latitude] corners.
SQUARE_CORNERS = [
    [79.6581, 29.5971],
    [79.6601, 29.5971],
    [79.6601, 29.5983],
    [79.6581, 29.5983],
    [79.6581, 29.5971],
]


class TestCoordinateValidation:
    @pytest.mark.parametrize("latitude", [91, -91, 1000, "north"])
    def test_invalid_latitude_is_rejected(self, latitude):
        with pytest.raises(ValidationFailed):
            validators.validate_latitude(latitude)

    @pytest.mark.parametrize("longitude", [181, -181, "east"])
    def test_invalid_longitude_is_rejected(self, longitude):
        with pytest.raises(ValidationFailed):
            validators.validate_longitude(longitude)

    def test_boundary_values_are_accepted(self):
        assert validators.validate_latitude(90) == 90
        assert validators.validate_longitude(-180) == -180

    def test_zero_is_a_valid_coordinate(self):
        assert validators.validate_latitude(0) == 0.0
        assert validators.validate_longitude(0) == 0.0

    def test_negative_accuracy_is_rejected(self):
        with pytest.raises(ValidationFailed):
            validators.validate_accuracy(-1)

    def test_absurd_accuracy_is_rejected(self):
        with pytest.raises(ValidationFailed):
            validators.validate_accuracy(50_000)


class TestRadiusValidation:
    def test_radius_below_the_minimum_is_rejected(self):
        with pytest.raises(ValidationFailed):
            validators.validate_radius(1)

    def test_radius_above_the_maximum_is_rejected(self):
        with pytest.raises(ValidationFailed):
            validators.validate_radius(10**9)

    def test_typical_radius_is_accepted(self):
        assert validators.validate_radius(150) == 150.0


class TestBoundingBoxValidation:
    def test_valid_box(self):
        box = validators.validate_bounding_box(**SQUARE_BOX)
        assert box == pytest.approx(SQUARE_BOX)

    def test_swapped_latitudes_are_rejected_not_corrected(self):
        """A swap almost always means lat/lon confusion; never silently fix it."""
        with pytest.raises(ValidationFailed) as error:
            validators.validate_bounding_box(
                min_latitude=SQUARE_BOX["max_latitude"],
                max_latitude=SQUARE_BOX["min_latitude"],
                min_longitude=SQUARE_BOX["min_longitude"],
                max_longitude=SQUARE_BOX["max_longitude"],
            )
        assert "max_latitude" in error.value.errors

    def test_swapped_longitudes_are_rejected(self):
        with pytest.raises(ValidationFailed) as error:
            validators.validate_bounding_box(
                min_latitude=SQUARE_BOX["min_latitude"],
                max_latitude=SQUARE_BOX["max_latitude"],
                min_longitude=SQUARE_BOX["max_longitude"],
                max_longitude=SQUARE_BOX["min_longitude"],
            )
        assert "max_longitude" in error.value.errors

    def test_zero_area_box_is_rejected(self):
        with pytest.raises(ValidationFailed):
            validators.validate_bounding_box(
                min_latitude=29.5971,
                max_latitude=29.5971,
                min_longitude=79.6581,
                max_longitude=79.6601,
            )

    def test_sub_metre_box_is_rejected(self):
        tiny = 0.1 / METRES_PER_DEGREE_LATITUDE
        with pytest.raises(ValidationFailed):
            validators.validate_bounding_box(
                min_latitude=29.5971,
                max_latitude=29.5971 + tiny,
                min_longitude=79.6581,
                max_longitude=79.6581 + tiny,
            )

    def test_absurdly_large_box_is_rejected(self):
        with pytest.raises(ValidationFailed):
            validators.validate_bounding_box(
                min_latitude=0.0,
                max_latitude=40.0,
                min_longitude=0.0,
                max_longitude=40.0,
            )

    def test_out_of_range_edge_is_rejected(self):
        with pytest.raises(ValidationFailed):
            validators.validate_bounding_box(
                min_latitude=29.5971,
                max_latitude=29.5983,
                min_longitude=79.6581,
                max_longitude=200.0,
            )

    def test_non_numeric_edge_is_rejected(self):
        with pytest.raises(ValidationFailed):
            validators.validate_bounding_box(
                min_latitude="south",
                max_latitude=29.5983,
                min_longitude=79.6581,
                max_longitude=79.6601,
            )


class TestBoundingBoxFromCorners:
    def test_extent_of_a_ring(self):
        box = validators.bounding_box_from_corners(SQUARE_CORNERS)
        assert box["min_latitude"] == pytest.approx(29.5971)
        assert box["max_latitude"] == pytest.approx(29.5983)
        assert box["min_longitude"] == pytest.approx(79.6581)
        assert box["max_longitude"] == pytest.approx(79.6601)

    def test_two_opposite_corners_are_enough(self):
        box = validators.bounding_box_from_corners(
            [[79.6601, 29.5983], [79.6581, 29.5971]]
        )
        assert box["min_latitude"] == pytest.approx(29.5971)
        assert box["max_longitude"] == pytest.approx(79.6601)

    def test_a_single_corner_is_rejected(self):
        with pytest.raises(ValidationFailed):
            validators.bounding_box_from_corners([[79.6581, 29.5971]])

    def test_malformed_vertex_is_rejected(self):
        with pytest.raises(ValidationFailed):
            validators.bounding_box_from_corners([[79.65, 29.59], [79.66]])

    def test_out_of_range_vertex_is_rejected(self):
        with pytest.raises(ValidationFailed):
            validators.bounding_box_from_corners([[79.65, 29.59], [200.0, 29.60]])


class TestHysteresisValidation:
    def test_circle_defaults_are_derived_from_the_radius(self):
        entry, exit_ = validators.validate_hysteresis(
            geofence_type=GeofenceType.CIRCLE,
            radius=150,
            entry_radius=None,
            exit_radius=None,
        )
        assert entry == 150.0
        assert exit_ == 190.0

    def test_exit_must_exceed_entry(self):
        with pytest.raises(ValidationFailed) as error:
            validators.validate_hysteresis(
                geofence_type=GeofenceType.CIRCLE,
                radius=150,
                entry_radius=120,
                exit_radius=80,
            )
        assert "exit_radius" in error.value.errors

    def test_equal_thresholds_are_rejected(self):
        with pytest.raises(ValidationFailed):
            validators.validate_hysteresis(
                geofence_type=GeofenceType.CIRCLE,
                radius=150,
                entry_radius=100,
                exit_radius=100,
            )

    def test_rectangle_buffers_default_to_configuration(self):
        entry, exit_ = validators.validate_hysteresis(
            geofence_type=GeofenceType.RECTANGLE,
            radius=None,
            entry_radius=None,
            exit_radius=None,
        )
        assert entry == 0.0
        assert exit_ == 40.0


@pytest.mark.django_db
class TestGeofenceService:
    def test_create_circle(self, organization):
        geofence = services.create_geofence(
            organization=organization,
            name="College Campus",
            geofence_type=GeofenceType.CIRCLE,
            latitude=CAMPUS_LATITUDE,
            longitude=CAMPUS_LONGITUDE,
            radius=150,
        )
        assert geofence.center_latitude == pytest.approx(CAMPUS_LATITUDE)
        assert geofence.center_longitude == pytest.approx(CAMPUS_LONGITUDE)
        assert geofence.effective_entry_threshold_m == 150.0
        assert geofence.effective_exit_threshold_m == 190.0

    def test_creating_a_circle_derives_its_bounding_box(self, organization):
        geofence = services.create_geofence(
            organization=organization,
            name="College Campus",
            geofence_type=GeofenceType.CIRCLE,
            latitude=CAMPUS_LATITUDE,
            longitude=CAMPUS_LONGITUDE,
            radius=150,
        )
        half_height_m = (
            (geofence.max_latitude - geofence.min_latitude)
            / 2
            * METRES_PER_DEGREE_LATITUDE
        )
        half_width_m = (
            (geofence.max_longitude - geofence.min_longitude)
            / 2
            * metres_per_degree_longitude(CAMPUS_LATITUDE)
        )
        assert half_height_m == pytest.approx(150, abs=1)
        assert half_width_m == pytest.approx(150, abs=1)

    def test_create_rectangle(self, organization):
        geofence = services.create_geofence(
            organization=organization,
            name="College Campus",
            geofence_type=GeofenceType.RECTANGLE,
            **SQUARE_BOX,
        )
        assert geofence.center_latitude is None
        assert geofence.center_longitude is None
        assert geofence.radius is None
        assert geofence.min_latitude == pytest.approx(SQUARE_BOX["min_latitude"])
        assert geofence.max_longitude == pytest.approx(SQUARE_BOX["max_longitude"])

    def test_circle_requires_a_radius(self, organization):
        with pytest.raises(ValidationFailed) as error:
            services.create_geofence(
                organization=organization,
                name="Broken",
                geofence_type=GeofenceType.CIRCLE,
                latitude=CAMPUS_LATITUDE,
                longitude=CAMPUS_LONGITUDE,
            )
        assert "radius" in error.value.errors

    def test_rectangle_requires_all_four_edges(self, organization):
        with pytest.raises(ValidationFailed) as error:
            services.create_geofence(
                organization=organization,
                name="Broken",
                geofence_type=GeofenceType.RECTANGLE,
                min_latitude=29.5971,
                max_latitude=29.5983,
                min_longitude=79.6581,
            )
        assert "max_longitude" in error.value.errors

    def test_duplicate_name_in_the_same_organization_conflicts(self, organization):
        from common.exceptions import Conflict

        kwargs = dict(
            organization=organization,
            name="Campus",
            geofence_type=GeofenceType.CIRCLE,
            latitude=CAMPUS_LATITUDE,
            longitude=CAMPUS_LONGITUDE,
            radius=150,
        )
        services.create_geofence(**kwargs)
        with pytest.raises(Conflict):
            services.create_geofence(**kwargs)

    def test_same_name_in_another_organization_is_fine(
        self, organization, other_organization
    ):
        for org in (organization, other_organization):
            services.create_geofence(
                organization=org,
                name="Campus",
                geofence_type=GeofenceType.CIRCLE,
                latitude=CAMPUS_LATITUDE,
                longitude=CAMPUS_LONGITUDE,
                radius=150,
            )

    def test_updating_the_radius_recomputes_the_thresholds(self, organization):
        geofence = services.create_geofence(
            organization=organization,
            name="Campus",
            geofence_type=GeofenceType.CIRCLE,
            latitude=CAMPUS_LATITUDE,
            longitude=CAMPUS_LONGITUDE,
            radius=150,
        )
        geofence = services.update_geofence(geofence=geofence, radius=300)
        assert geofence.entry_radius == 300.0
        assert geofence.exit_radius == 340.0

    def test_updating_the_radius_regrows_the_bounding_box(self, organization):
        geofence = services.create_geofence(
            organization=organization,
            name="Campus",
            geofence_type=GeofenceType.CIRCLE,
            latitude=CAMPUS_LATITUDE,
            longitude=CAMPUS_LONGITUDE,
            radius=150,
        )
        before = geofence.max_latitude
        geofence = services.update_geofence(geofence=geofence, radius=300)
        geofence.refresh_from_db()
        assert geofence.max_latitude > before

    def test_moving_one_edge_keeps_the_other_three(self, organization):
        geofence = services.create_geofence(
            organization=organization,
            name="Campus",
            geofence_type=GeofenceType.RECTANGLE,
            **SQUARE_BOX,
        )
        geofence = services.update_geofence(
            geofence=geofence, max_latitude=SQUARE_BOX["max_latitude"] + 0.001
        )
        assert geofence.min_latitude == pytest.approx(SQUARE_BOX["min_latitude"])
        assert geofence.min_longitude == pytest.approx(SQUARE_BOX["min_longitude"])
        assert geofence.max_latitude == pytest.approx(
            SQUARE_BOX["max_latitude"] + 0.001
        )

    def test_switching_a_circle_to_a_rectangle(self, organization):
        geofence = services.create_geofence(
            organization=organization,
            name="Campus",
            geofence_type=GeofenceType.CIRCLE,
            latitude=CAMPUS_LATITUDE,
            longitude=CAMPUS_LONGITUDE,
            radius=150,
        )
        box = campus_bbox()
        geofence = services.update_geofence(
            geofence=geofence,
            geofence_type=GeofenceType.RECTANGLE,
            **box,
        )
        assert geofence.geofence_type == GeofenceType.RECTANGLE
        assert geofence.center_latitude is None
        assert geofence.radius is None

    def test_switching_a_rectangle_to_a_circle(self, organization):
        geofence = services.create_geofence(
            organization=organization,
            name="Campus",
            geofence_type=GeofenceType.RECTANGLE,
            **SQUARE_BOX,
        )
        geofence = services.update_geofence(
            geofence=geofence,
            geofence_type=GeofenceType.CIRCLE,
            latitude=CAMPUS_LATITUDE,
            longitude=CAMPUS_LONGITUDE,
            radius=150,
        )
        assert geofence.geofence_type == GeofenceType.CIRCLE
        assert geofence.center_latitude == pytest.approx(CAMPUS_LATITUDE)
        # The envelope now describes the circle, not the old box.
        assert geofence.max_latitude > CAMPUS_LATITUDE
