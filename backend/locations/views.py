"""Location API.

``POST /api/location/update/`` is the only write endpoint a tracked user calls.
It is deliberately small: validate, hand the payload to the presence service,
and render whatever the backend decided.
"""
from __future__ import annotations

from typing import Any

from django_filters import rest_framework as filters
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from common.conf import geo_conf
from common.mixins import OrganizationScopedMixin
from common.pagination import LargePagination
from common.permissions import IsOrganizationAdmin, IsOrganizationMember
from common.throttling import UserScopedRateThrottle
from locations import selectors as location_selectors
from locations.models import LocationAnomaly, LocationUpdate
from locations.serializers import (
    AnomalySerializer,
    LocationStatusResponseSerializer,
    LocationUpdateRequestSerializer,
    LocationUpdateResponseSerializer,
    LocationUpdateSerializer,
)
from locations.validators import validate_location_payload
from presence import selectors as presence_selectors
from presence.enums import PresenceStatus
from presence.services.processing import LocationIngestResult, process_location_update


def _serialize_outcomes(result: LocationIngestResult) -> list[dict[str, Any]]:
    outcomes = []
    for outcome in result.outcomes:
        presence = outcome.presence
        evaluation = outcome.evaluation
        outcomes.append(
            {
                "geofence_id": evaluation.geofence_id,
                "geofence_name": evaluation.geofence_name,
                "status": outcome.status,
                "previous_status": outcome.previous_status,
                "changed": outcome.changed,
                "applied": outcome.applied,
                "skip_reason": outcome.skip_reason,
                "events": outcome.events,
                "verdict": evaluation.verdict,
                "confidence": evaluation.confidence,
                "distance_to_boundary_m": round(evaluation.distance_to_boundary_m, 2),
                "accuracy_margin_m": round(evaluation.accuracy_margin_m, 2),
                "consecutive_inside": presence.consecutive_inside,
                "consecutive_outside": presence.consecutive_outside,
                "required_inside_readings": evaluation.required_inside_readings,
                "required_outside_readings": evaluation.required_outside_readings,
                "check_in_at": presence.check_in_at,
                "check_out_at": presence.check_out_at,
                "last_seen_at": presence.last_seen_at,
            }
        )
    return outcomes


def _serialize_ingest_result(*, user, result: LocationIngestResult) -> dict[str, Any]:
    """Render the authoritative answer to a location update."""
    day = presence_selectors.attendance_date_for(user)
    rows = list(presence_selectors.presence_rows_for_user(user.pk, day=day))

    return {
        "location_update_id": result.location_update.pk,
        "duplicate": result.duplicate,
        "trusted": result.trusted,
        "skipped_reason": result.skipped_reason,
        "recorded_at": result.location_update.recorded_at,
        "received_at": result.location_update.received_at,
        "effective_status": presence_selectors.effective_status(rows),
        "presence": _serialize_outcomes(result),
        "evaluations": [evaluation.as_dict() for evaluation in result.evaluations],
        "anomalies": [
            {
                "type": anomaly.anomaly_type,
                "severity": anomaly.severity,
                "details": anomaly.details,
            }
            for anomaly in result.anomalies
        ],
        "next_ping_seconds": geo_conf.RECOMMENDED_PING_INTERVAL_SECONDS,
    }


@extend_schema(tags=["location"])
class LocationUpdateView(APIView):
    """Accept one GPS observation and return the resulting presence state."""

    permission_classes = (IsOrganizationMember,)
    throttle_classes = (UserScopedRateThrottle,)
    throttle_scope = "location_update"
    serializer_class = LocationUpdateRequestSerializer

    @extend_schema(
        request=LocationUpdateRequestSerializer,
        responses={200: LocationUpdateResponseSerializer, 201: LocationUpdateResponseSerializer},
        summary="Submit a location update",
        description=(
            "The backend decides presence. Clients must never send a status. "
            "Supply `client_event_id` to make retries idempotent."
        ),
        examples=[
            OpenApiExample(
                "Typical fix",
                value={
                    "latitude": 29.59791,
                    "longitude": 79.65887,
                    "accuracy": 12,
                    "recorded_at": "2026-08-26T12:20:15Z",
                    "client_event_id": "5f0f1f6e-2f2a-4f43-bd0f-1a3c5f9a0e11",
                },
                request_only=True,
            )
        ],
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = LocationUpdateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payload = validate_location_payload(dict(serializer.validated_data))
        result = process_location_update(user=request.user, payload=payload)

        body = _serialize_ingest_result(user=request.user, result=result)
        http_status = status.HTTP_200_OK if result.duplicate else status.HTTP_201_CREATED
        return Response(body, status=http_status)


@extend_schema(tags=["location"])
class LocationStatusView(APIView):
    """What the backend currently believes about the caller.

    Also returns the tuning the client should honour, so the PWA never
    hard-codes an interval or an accuracy threshold.
    """

    permission_classes = (IsOrganizationMember,)
    throttle_scope = "read"

    @extend_schema(
        responses={200: LocationStatusResponseSerializer},
        summary="Current location/presence status of the caller",
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        user = request.user
        last_update = location_selectors.last_update_for_user(user.pk)
        day = presence_selectors.attendance_date_for(user)
        rows = list(presence_selectors.presence_rows_for_user(user.pk, day=day))
        effective = presence_selectors.effective_presence(rows)

        return Response(
            {
                "date": day,
                "effective_status": (
                    effective.status if effective else PresenceStatus.UNKNOWN
                ),
                "geofence_id": effective.geofence_id if effective else None,
                "geofence_name": effective.geofence.name if effective else None,
                "check_in_at": effective.check_in_at if effective else None,
                "check_out_at": effective.check_out_at if effective else None,
                "last_seen_at": effective.last_seen_at if effective else None,
                "last_location": (
                    {
                        "latitude": last_update.latitude,
                        "longitude": last_update.longitude,
                        "accuracy": last_update.accuracy,
                        "recorded_at": last_update.recorded_at,
                        "received_at": last_update.received_at,
                        "confidence": last_update.confidence,
                        "is_trusted": last_update.is_trusted,
                    }
                    if last_update
                    else None
                ),
                "client_config": {
                    "recommended_ping_interval_seconds": geo_conf.RECOMMENDED_PING_INTERVAL_SECONDS,
                    "max_acceptable_accuracy_m": geo_conf.MAX_ACCEPTABLE_ACCURACY_M,
                    "stale_after_seconds": geo_conf.STALE_AFTER_SECONDS,
                    "max_location_age_seconds": geo_conf.MAX_LOCATION_AGE_SECONDS,
                },
            }
        )


class LocationUpdateFilterSet(filters.FilterSet):
    recorded_after = filters.IsoDateTimeFilter(field_name="recorded_at", lookup_expr="gte")
    recorded_before = filters.IsoDateTimeFilter(field_name="recorded_at", lookup_expr="lte")
    is_flagged = filters.BooleanFilter(field_name="is_flagged")
    is_trusted = filters.BooleanFilter(field_name="is_trusted")

    class Meta:
        model = LocationUpdate
        fields = ("is_flagged", "is_trusted")


@extend_schema(tags=["location"])
class MyLocationHistoryView(generics.ListAPIView):
    """The caller's own stored fixes (privacy: never another user's)."""

    serializer_class = LocationUpdateSerializer
    permission_classes = (IsOrganizationMember,)
    pagination_class = LargePagination
    filterset_class = LocationUpdateFilterSet
    throttle_scope = "read"

    def get_queryset(self):
        return location_selectors.user_location_history(self.request.user.pk).prefetch_related(
            "anomalies"
        )


class AnomalyFilterSet(filters.FilterSet):
    user = filters.NumberFilter(field_name="user_id")
    anomaly_type = filters.CharFilter(field_name="anomaly_type", lookup_expr="iexact")
    severity = filters.CharFilter(field_name="severity", lookup_expr="iexact")
    created_after = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = LocationAnomaly
        fields = ("user", "anomaly_type", "severity")


@extend_schema(tags=["admin"])
class AnomalyListView(OrganizationScopedMixin, generics.ListAPIView):
    """Anomaly feed for administrators.

    Deliberately read-only and advisory: nothing here bans or blocks anybody.
    """

    serializer_class = AnomalySerializer
    permission_classes = (IsOrganizationAdmin,)
    filterset_class = AnomalyFilterSet
    queryset = LocationAnomaly.objects.select_related("user", "location_update")
    ordering_fields = ("created_at", "severity")
    ordering = ("-created_at",)
    throttle_scope = "read"
