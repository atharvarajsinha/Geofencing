"""Geofence evaluation: the pure verdict function and the candidate query."""
from __future__ import annotations

import pytest
from django.test import override_settings

from geofences.enums import ContainmentVerdict, ReadingConfidence
from geofences.evaluation import (
    accuracy_margin_m,
    classify,
    evaluate_point,
    reading_confidence,
)
from tests.conftest import offset_point


class TestClassify:
    """Pure policy: no database involved."""

    def test_confidently_inside(self):
        assert (
            classify(
                axis_value_m=60, margin_m=10, entry_threshold_m=80, exit_threshold_m=120
            )
            == ContainmentVerdict.INSIDE
        )

    def test_confidently_outside(self):
        assert (
            classify(
                axis_value_m=200, margin_m=10, entry_threshold_m=80, exit_threshold_m=120
            )
            == ContainmentVerdict.OUTSIDE
        )

    def test_hysteresis_band_is_uncertain(self):
        assert (
            classify(
                axis_value_m=100, margin_m=1, entry_threshold_m=80, exit_threshold_m=120
            )
            == ContainmentVerdict.UNCERTAIN
        )

    def test_poor_accuracy_cannot_prove_containment(self):
        """Same position, different accuracy, different verdict."""
        precise = classify(
            axis_value_m=60, margin_m=10, entry_threshold_m=80, exit_threshold_m=120
        )
        imprecise = classify(
            axis_value_m=60, margin_m=100, entry_threshold_m=80, exit_threshold_m=120
        )
        assert precise == ContainmentVerdict.INSIDE
        assert imprecise == ContainmentVerdict.UNCERTAIN

    def test_poor_accuracy_cannot_prove_departure_either(self):
        assert (
            classify(
                axis_value_m=130, margin_m=100, entry_threshold_m=80, exit_threshold_m=120
            )
            == ContainmentVerdict.UNCERTAIN
        )

    def test_margin_is_capped(self):
        with override_settings(
            GEOFENCING={"ACCURACY_MARGIN_CAP_M": 150.0, "ACCURACY_MARGIN_FACTOR": 1.0}
        ):
            assert accuracy_margin_m(5_000) == 150.0

    def test_margin_factor_is_configurable(self):
        with override_settings(GEOFENCING={"ACCURACY_MARGIN_FACTOR": 0.5}):
            assert accuracy_margin_m(40) == 20.0

    def test_missing_accuracy_is_treated_as_the_worst_acceptable(self):
        assert accuracy_margin_m(None) > 0

    def test_confidence_follows_the_accuracy_threshold(self):
        assert reading_confidence(10) == ReadingConfidence.HIGH
        assert reading_confidence(500) == ReadingConfidence.LOW


@pytest.mark.django_db
class TestCircleEvaluation:
    def test_point_at_the_centre_is_inside(self, organization, circle_geofence, campus_centre):
        latitude, longitude = campus_centre
        [(geofence, evaluation)] = evaluate_point(
            organization_id=organization.pk,
            latitude=latitude,
            longitude=longitude,
            accuracy=10,
        )
        assert geofence.pk == circle_geofence.pk
        assert evaluation.verdict == ContainmentVerdict.INSIDE
        assert evaluation.distance_to_boundary_m == pytest.approx(-150, abs=2)

    def test_point_far_away_is_outside(self, organization, circle_geofence):
        latitude, longitude = offset_point(metres_north=400)
        [(_, evaluation)] = evaluate_point(
            organization_id=organization.pk,
            latitude=latitude,
            longitude=longitude,
            accuracy=10,
        )
        assert evaluation.verdict == ContainmentVerdict.OUTSIDE

    def test_point_in_the_hysteresis_band_is_uncertain(self, organization, circle_geofence):
        # 170 m from the centre: past the 150 m entry radius, short of the 190 m
        # exit radius.
        latitude, longitude = offset_point(metres_north=170)
        [(_, evaluation)] = evaluate_point(
            organization_id=organization.pk,
            latitude=latitude,
            longitude=longitude,
            accuracy=5,
        )
        assert evaluation.verdict == ContainmentVerdict.UNCERTAIN

    def test_distance_matches_the_requested_offset(self, organization, circle_geofence):
        latitude, longitude = offset_point(metres_east=100)
        [(_, evaluation)] = evaluate_point(
            organization_id=organization.pk,
            latitude=latitude,
            longitude=longitude,
            accuracy=5,
        )
        assert evaluation.axis_value_m == pytest.approx(100, abs=3)

    def test_inactive_geofences_are_skipped(self, organization, circle_geofence, campus_centre):
        circle_geofence.is_active = False
        circle_geofence.save(update_fields=["is_active"])
        latitude, longitude = campus_centre
        assert (
            evaluate_point(
                organization_id=organization.pk,
                latitude=latitude,
                longitude=longitude,
                accuracy=10,
            )
            == []
        )

    def test_inactive_geofence_is_still_evaluated_when_explicitly_included(
        self, organization, circle_geofence, campus_centre
    ):
        """A retired geofence must still be able to check people out."""
        circle_geofence.is_active = False
        circle_geofence.save(update_fields=["is_active"])
        latitude, longitude = campus_centre
        results = evaluate_point(
            organization_id=organization.pk,
            latitude=latitude,
            longitude=longitude,
            accuracy=10,
            include_geofence_ids=(circle_geofence.pk,),
        )
        assert len(results) == 1

    def test_other_organizations_are_never_evaluated(
        self, organization, other_organization, circle_geofence, campus_centre
    ):
        latitude, longitude = campus_centre
        assert (
            evaluate_point(
                organization_id=other_organization.pk,
                latitude=latitude,
                longitude=longitude,
                accuracy=10,
            )
            == []
        )


@pytest.mark.django_db
class TestRectangleEvaluation:
    def test_point_inside_the_rectangle(self, organization, rectangle_geofence, campus_centre):
        latitude, longitude = campus_centre
        [(_, evaluation)] = evaluate_point(
            organization_id=organization.pk,
            latitude=latitude,
            longitude=longitude,
            accuracy=10,
        )
        assert evaluation.verdict == ContainmentVerdict.INSIDE
        # Negative distance means "inside, this far from the boundary".
        assert evaluation.distance_to_boundary_m < 0

    def test_point_outside_the_rectangle(self, organization, rectangle_geofence):
        latitude, longitude = offset_point(metres_north=500)
        [(_, evaluation)] = evaluate_point(
            organization_id=organization.pk,
            latitude=latitude,
            longitude=longitude,
            accuracy=10,
        )
        assert evaluation.verdict == ContainmentVerdict.OUTSIDE
        assert evaluation.distance_to_boundary_m > 0

    def test_just_outside_but_within_the_exit_buffer_is_uncertain(
        self, organization, rectangle_geofence
    ):
        # The square reaches 200 m north; 220 m is outside the boundary but
        # inside the 40 m exit outset.
        latitude, longitude = offset_point(metres_north=220)
        [(_, evaluation)] = evaluate_point(
            organization_id=organization.pk,
            latitude=latitude,
            longitude=longitude,
            accuracy=5,
        )
        assert evaluation.verdict == ContainmentVerdict.UNCERTAIN

    def test_inside_but_within_the_accuracy_margin_of_the_edge(
        self, organization, rectangle_geofence
    ):
        latitude, longitude = offset_point(metres_north=195)
        [(_, evaluation)] = evaluate_point(
            organization_id=organization.pk,
            latitude=latitude,
            longitude=longitude,
            accuracy=30,
        )
        assert evaluation.verdict == ContainmentVerdict.UNCERTAIN
