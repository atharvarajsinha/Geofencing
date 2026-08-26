"""The geofence evaluator: the single place that decides inside vs outside.

Design in one paragraph
-----------------------
Every geofence is reduced to one comparison axis (see :mod:`geofences.models`).
``Geofence.axis_value_m`` computes the position of the GPS fix on that axis in
pure Python - no PostGIS, no GEOS, no GDAL - and this module applies the policy.
Reported GPS accuracy is turned into an uncertainty margin ``m`` and the verdict
is deliberately conservative:

* ``INSIDE``    when ``x + m <= entry_threshold`` - the whole accuracy circle
  is inside the entry boundary,
* ``OUTSIDE``   when ``x - m >= exit_threshold``  - the whole accuracy circle
  is beyond the exit boundary,
* ``UNCERTAIN`` otherwise - either the device is in the hysteresis band, or the
  fix is too imprecise to tell. An ``UNCERTAIN`` reading never changes state.

Two fixes at the same distance are therefore *not* interchangeable. Against an
``entry_radius`` of 80 m:

* ``distance=60 m, accuracy=10 m`` -> 70 <= 80 -> ``INSIDE``,
* ``distance=60 m, accuracy=100 m`` -> 160 > 80, and 60 - 100 is far below the
  exit threshold -> ``UNCERTAIN``: the device is probably inside but the fix
  cannot prove it, so the state is left untouched,
* ``distance=75 m, accuracy=10 m`` -> 85 > 80 -> still ``UNCERTAIN``; the user
  checks in a few metres further in, or on the next fix with better accuracy.

Deployments that find full-margin behaviour too strict lower
``ACCURACY_MARGIN_FACTOR`` (0.5 uses half the accuracy radius) instead of
widening the geofence, which would also weaken the exit test.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Sequence

from django.db.models import Q

from common.conf import geo_conf
from geofences.enums import ContainmentVerdict, ReadingConfidence
from geofences.models import Geofence

logger = logging.getLogger("geofencing.evaluation")


@dataclass(frozen=True)
class GeofenceEvaluation:
    """Outcome of comparing one fix against one geofence."""

    geofence_id: int
    geofence_name: str
    geofence_type: str
    verdict: str
    confidence: str
    #: Position of the fix on the comparison axis (metres).
    axis_value_m: float
    #: Signed distance to the drawn boundary; negative inside.
    distance_to_boundary_m: float
    accuracy_m: float
    accuracy_margin_m: float
    entry_threshold_m: float
    exit_threshold_m: float
    required_inside_readings: int
    required_outside_readings: int

    @property
    def is_inside(self) -> bool:
        return self.verdict == ContainmentVerdict.INSIDE

    @property
    def is_outside(self) -> bool:
        return self.verdict == ContainmentVerdict.OUTSIDE

    @property
    def is_uncertain(self) -> bool:
        return self.verdict == ContainmentVerdict.UNCERTAIN

    def as_dict(self) -> dict[str, object]:
        return {
            "geofence_id": self.geofence_id,
            "geofence_name": self.geofence_name,
            "geofence_type": self.geofence_type,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "distance_to_boundary_m": round(self.distance_to_boundary_m, 2),
            "accuracy_m": round(self.accuracy_m, 2),
            "accuracy_margin_m": round(self.accuracy_margin_m, 2),
            "entry_threshold_m": round(self.entry_threshold_m, 2),
            "exit_threshold_m": round(self.exit_threshold_m, 2),
        }


def accuracy_margin_m(accuracy: float | None) -> float:
    """Uncertainty margin derived from the reported GPS accuracy.

    Capped so that a single nonsense accuracy value (browsers occasionally
    report kilometres when falling back to IP geolocation) cannot make every
    verdict UNCERTAIN forever.
    """
    if accuracy is None:
        # No accuracy reported: assume the worst still-acceptable fix rather
        # than assuming perfection.
        accuracy = geo_conf.MAX_ACCEPTABLE_ACCURACY_M
    bounded = min(max(float(accuracy), 0.0), geo_conf.ACCURACY_MARGIN_CAP_M)
    return bounded * geo_conf.ACCURACY_MARGIN_FACTOR


def reading_confidence(accuracy: float | None) -> str:
    if accuracy is None:
        return ReadingConfidence.LOW
    return (
        ReadingConfidence.HIGH
        if float(accuracy) <= geo_conf.MAX_ACCEPTABLE_ACCURACY_M
        else ReadingConfidence.LOW
    )


def classify(
    *,
    axis_value_m: float,
    margin_m: float,
    entry_threshold_m: float,
    exit_threshold_m: float,
) -> str:
    """Pure verdict function - no database, no models, trivially testable."""
    if axis_value_m + margin_m <= entry_threshold_m:
        return ContainmentVerdict.INSIDE
    if axis_value_m - margin_m >= exit_threshold_m:
        return ContainmentVerdict.OUTSIDE
    return ContainmentVerdict.UNCERTAIN


def _candidate_queryset(
    *,
    organization_id: int,
    include_geofence_ids: Sequence[int] = (),
    only_active: bool = True,
):
    """Geofences of the organization that a fix must be compared against.

    No geometry is loaded and no distance is computed in SQL: rows come back as
    ordinary floats and :func:`_evaluate_row` does the maths. Only the
    per-update cap is applied here, so the query is a plain indexed filter.
    """
    queryset = Geofence.objects.filter(organization_id=organization_id)

    if only_active:
        visibility = Q(is_active=True)
        if include_geofence_ids:
            # A geofence that was deactivated while somebody was checked in must
            # still be evaluated, otherwise that user could never be checked out.
            visibility |= Q(pk__in=list(include_geofence_ids))
        queryset = queryset.filter(visibility)

    return queryset.order_by("id")[: geo_conf.MAX_GEOFENCES_EVALUATED_PER_UPDATE]


def _evaluate_row(
    geofence: Geofence,
    latitude: float,
    longitude: float,
    accuracy: float | None,
) -> GeofenceEvaluation | None:
    """Turn one geofence row plus one fix into a verdict."""
    margin = accuracy_margin_m(accuracy)
    entry_threshold = geofence.effective_entry_threshold_m
    exit_threshold = geofence.effective_exit_threshold_m

    try:
        axis_value = geofence.axis_value_m(latitude, longitude)
        boundary_distance = geofence.signed_distance_m(latitude, longitude)
    except (TypeError, ValueError):
        # A row whose shape columns are incomplete cannot be judged. Skipping is
        # the right call: raising here would reject the whole location update
        # because of one malformed geofence.
        logger.warning(
            "Geofence %s (%s) has an unusable shape; skipping evaluation.",
            geofence.pk,
            geofence.geofence_type,
        )
        return None

    verdict = classify(
        axis_value_m=axis_value,
        margin_m=margin,
        entry_threshold_m=entry_threshold,
        exit_threshold_m=exit_threshold,
    )

    return GeofenceEvaluation(
        geofence_id=geofence.pk,
        geofence_name=geofence.name,
        geofence_type=geofence.geofence_type,
        verdict=verdict,
        confidence=reading_confidence(accuracy),
        axis_value_m=float(axis_value),
        distance_to_boundary_m=float(boundary_distance),
        accuracy_m=float(accuracy if accuracy is not None else geo_conf.MAX_ACCEPTABLE_ACCURACY_M),
        accuracy_margin_m=margin,
        entry_threshold_m=entry_threshold,
        exit_threshold_m=exit_threshold,
        required_inside_readings=geofence.effective_required_inside_readings,
        required_outside_readings=geofence.effective_required_outside_readings,
    )


def evaluate_point(
    *,
    organization_id: int,
    latitude: float,
    longitude: float,
    accuracy: float | None,
    include_geofence_ids: Sequence[int] = (),
    only_active: bool = True,
) -> list[tuple[Geofence, GeofenceEvaluation]]:
    """Evaluate one fix against every relevant geofence in one query.

    Returns ``(geofence, evaluation)`` pairs; the caller needs the model
    instances to create or update presence rows without re-querying.
    """
    results: list[tuple[Geofence, GeofenceEvaluation]] = []
    for geofence in _candidate_queryset(
        organization_id=organization_id,
        include_geofence_ids=include_geofence_ids,
        only_active=only_active,
    ):
        evaluation = _evaluate_row(geofence, latitude, longitude, accuracy)
        if evaluation is not None:
            results.append((geofence, evaluation))
    return results


def best_inside(
    evaluations: Iterable[tuple[Geofence, GeofenceEvaluation]]
) -> tuple[Geofence, GeofenceEvaluation] | None:
    """The geofence the device is most convincingly inside of, if any."""
    inside = [pair for pair in evaluations if pair[1].is_inside]
    if not inside:
        return None
    return min(inside, key=lambda pair: pair[1].distance_to_boundary_m)
