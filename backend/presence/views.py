"""Presence API: self-service endpoints and the admin dashboard."""
from __future__ import annotations

from datetime import date as date_type
from typing import Any

from django.utils.dateparse import parse_date
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from common.exceptions import NotFound, ValidationFailed
from common.mixins import OrganizationScopedMixin
from common.pagination import DefaultPagination, LargePagination
from common.permissions import IsOrganizationAdmin, IsOrganizationMember
from presence import selectors
from presence.filters import PresenceEventFilterSet, PresenceFilterSet
from presence.models import Presence, PresenceEvent
from presence.serializers import (
    AdminUserPresenceSerializer,
    MyPresenceSerializer,
    PresenceEventSerializer,
    PresenceSerializer,
    PresenceSummarySerializer,
)


def _requested_date(request: Request, user) -> date_type:
    """``?date=YYYY-MM-DD`` or today in the organization's timezone."""
    raw = request.query_params.get("date")
    if not raw:
        return selectors.attendance_date_for(user)
    parsed = parse_date(raw)
    if parsed is None:
        raise ValidationFailed(errors={"date": ["Expected a date in YYYY-MM-DD form."]})
    return parsed


@extend_schema(tags=["presence"])
class MyPresenceView(APIView):
    """The caller's presence for one attendance day (default: today)."""

    permission_classes = (IsOrganizationMember,)
    throttle_scope = "read"

    @extend_schema(
        responses={200: MyPresenceSerializer},
        parameters=[OpenApiParameter("date", str, description="YYYY-MM-DD")],
        summary="My presence",
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        day = _requested_date(request, request.user)
        rows = list(selectors.presence_rows_for_user(request.user.pk, day=day))
        return Response(
            {
                "date": day,
                "effective_status": selectors.effective_status(rows),
                "geofences": PresenceSerializer(rows, many=True).data,
            }
        )


@extend_schema(tags=["presence"])
class MyPresenceHistoryView(generics.ListAPIView):
    """The caller's own presence records over time."""

    serializer_class = PresenceSerializer
    permission_classes = (IsOrganizationMember,)
    pagination_class = LargePagination
    filterset_class = PresenceFilterSet
    ordering_fields = ("date", "check_in_at", "last_seen_at")
    ordering = ("-date",)
    throttle_scope = "read"

    def get_queryset(self):
        return selectors.presence_rows_for_user(self.request.user.pk)


@extend_schema(tags=["presence"])
class MyPresenceEventsView(generics.ListAPIView):
    """The caller's own audit trail."""

    serializer_class = PresenceEventSerializer
    permission_classes = (IsOrganizationMember,)
    pagination_class = LargePagination
    filterset_class = PresenceEventFilterSet
    ordering_fields = ("timestamp",)
    ordering = ("-timestamp",)
    throttle_scope = "read"

    def get_queryset(self):
        return selectors.user_presence_events(self.request.user.pk)


@extend_schema(tags=["admin"])
class AdminPresenceListView(OrganizationScopedMixin, generics.ListAPIView):
    """Organization-wide presence records, filtered and paginated.

    ``GET /api/admin/presence/?status=PRESENT&date=2026-08-26``
    """

    serializer_class = PresenceSerializer
    permission_classes = (IsOrganizationAdmin,)
    pagination_class = DefaultPagination
    filterset_class = PresenceFilterSet
    queryset = Presence.objects.with_related()
    ordering_fields = ("date", "last_seen_at", "check_in_at", "status")
    ordering = ("-date", "user_id")
    throttle_scope = "read"

    def get_queryset(self):
        queryset = super().get_queryset()
        # Default to today so the dashboard's first request is cheap and
        # meaningful rather than a full table scan.
        params = self.request.query_params
        if not any(key in params for key in ("date", "date_from", "date_to")):
            queryset = queryset.filter(
                date=selectors.attendance_date_for(self.request.user)
            )
        return queryset


@extend_schema(tags=["admin"])
class AdminPresenceSummaryView(OrganizationScopedMixin, APIView):
    """Counters for the dashboard header."""

    permission_classes = (IsOrganizationAdmin,)
    throttle_scope = "read"
    organization_field = "organization"

    @extend_schema(
        responses={200: PresenceSummarySerializer},
        parameters=[
            OpenApiParameter("date", str, description="YYYY-MM-DD"),
            OpenApiParameter("geofence", int, description="Restrict to one geofence"),
        ],
        summary="Presence summary",
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        organization_id = self.effective_organization_id
        if organization_id is None:
            raise ValidationFailed(
                errors={
                    "organization": [
                        "Specify ?organization=<id>; a summary spanning tenants is "
                        "not meaningful."
                    ]
                }
            )
        day = _requested_date(request, request.user)
        geofence_id = request.query_params.get("geofence")

        summary = selectors.presence_summary(
            organization_id=organization_id,
            day=day,
            geofence_id=int(geofence_id) if geofence_id else None,
        )
        summary["by_geofence"] = selectors.geofence_occupancy(
            organization_id=organization_id, day=day
        )
        return Response(summary)


@extend_schema(tags=["admin"])
class AdminUserPresenceView(OrganizationScopedMixin, APIView):
    """Everything an admin needs about one member on one day."""

    permission_classes = (IsOrganizationAdmin,)
    throttle_scope = "read"

    @extend_schema(
        parameters=[OpenApiParameter("date", str, description="YYYY-MM-DD")],
        responses={200: AdminUserPresenceSerializer},
        summary="Presence detail for one user",
    )
    def get(self, request: Request, user_id: int, *args: Any, **kwargs: Any) -> Response:
        # Scope first: an admin of another organization must get a 404, not data.
        rows = list(
            self.scope_queryset_to_organization(Presence.objects.with_related())
            .filter(user_id=user_id)
            .order_by("-date", "geofence_id")[:100]
        )
        day = _requested_date(request, request.user)
        today_rows = [row for row in rows if row.date == day]

        if not rows:
            from accounts.selectors import visible_users_for

            if not visible_users_for(request.user).filter(pk=user_id).exists():
                raise NotFound("User not found in your organization.")

        events = list(
            self.scope_queryset_to_organization(PresenceEvent.objects.with_related())
            .filter(user_id=user_id)
            .order_by("-timestamp")[:50]
        )

        return Response(
            {
                "user_id": user_id,
                "date": day,
                "effective_status": selectors.effective_status(today_rows),
                "today": PresenceSerializer(today_rows, many=True).data,
                "recent": PresenceSerializer(rows, many=True).data,
                "events": PresenceEventSerializer(events, many=True).data,
            }
        )


@extend_schema(tags=["admin"])
class AdminPresenceEventListView(OrganizationScopedMixin, generics.ListAPIView):
    """Organization-wide audit trail."""

    serializer_class = PresenceEventSerializer
    permission_classes = (IsOrganizationAdmin,)
    pagination_class = DefaultPagination
    filterset_class = PresenceEventFilterSet
    queryset = PresenceEvent.objects.with_related()
    ordering_fields = ("timestamp", "event_type")
    ordering = ("-timestamp",)
    throttle_scope = "read"
