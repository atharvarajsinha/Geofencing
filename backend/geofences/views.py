"""Geofence API.

Reads are available to every member of the organization (the PWA draws the
area on a map); writes require an administrator.
"""
from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response

from common.exceptions import ValidationFailed
from common.mixins import OrganizationScopedMixin, SerializerContextMixin
from common.permissions import (
    BelongsToSameOrganization,
    ReadOnlyForMembersAdminForWrites,
)
from geofences import services
from geofences.filters import GeofenceFilterSet
from geofences.models import Geofence
from geofences.serializers import GeofenceSerializer, GeofenceWriteSerializer
from organizations.models import Organization


@extend_schema_view(
    list=extend_schema(summary="List geofences", tags=["geofences"]),
    retrieve=extend_schema(summary="Retrieve a geofence", tags=["geofences"]),
    create=extend_schema(
        summary="Create a geofence",
        tags=["geofences"],
        request=GeofenceWriteSerializer,
        responses={201: GeofenceSerializer},
        examples=[
            OpenApiExample(
                "Circle",
                value={
                    "name": "College Campus",
                    "type": "CIRCLE",
                    "latitude": 29.5976,
                    "longitude": 79.6591,
                    "radius": 150,
                },
                request_only=True,
            ),
            OpenApiExample(
                "Rectangle",
                value={
                    "name": "Academic Block",
                    "type": "RECTANGLE",
                    "min_latitude": 29.5971,
                    "max_latitude": 29.5983,
                    "min_longitude": 79.6581,
                    "max_longitude": 79.6601,
                },
                request_only=True,
            ),
        ],
    ),
    partial_update=extend_schema(
        summary="Update a geofence",
        tags=["geofences"],
        request=GeofenceWriteSerializer,
        responses={200: GeofenceSerializer},
    ),
    destroy=extend_schema(summary="Delete a geofence", tags=["geofences"]),
)
class GeofenceViewSet(
    OrganizationScopedMixin, SerializerContextMixin, viewsets.ModelViewSet
):
    serializer_class = GeofenceSerializer
    queryset = Geofence.objects.select_related("organization")
    permission_classes = (ReadOnlyForMembersAdminForWrites, BelongsToSameOrganization)
    filterset_class = GeofenceFilterSet
    ordering_fields = ("name", "created_at", "updated_at")
    ordering = ("name",)
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_throttles(self):
        self.throttle_scope = "read" if self.request.method in {"GET", "HEAD"} else "write"
        return super().get_throttles()

    def _target_organization(self) -> Organization:
        """Organization the new geofence belongs to.

        A platform admin must say which tenant they are acting for; everybody
        else can only ever create inside their own.
        """
        user = self.request.user
        if not user.is_platform_admin:
            return user.organization

        organization_id = self.request.data.get("organization") or self.request.query_params.get(
            "organization"
        )
        if not organization_id:
            raise ValidationFailed(
                errors={
                    "organization": [
                        "Platform administrators must specify the target organization."
                    ]
                }
            )
        organization = Organization.objects.filter(pk=organization_id).first()
        if organization is None:
            raise ValidationFailed(errors={"organization": ["Unknown organization."]})
        return organization

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = GeofenceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        geofence = services.create_geofence(
            organization=self._target_organization(),
            **serializer.to_service_kwargs(),
        )
        return Response(
            GeofenceSerializer(geofence).data, status=status.HTTP_201_CREATED
        )

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        geofence = self.get_object()
        serializer = GeofenceWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        payload = serializer.to_service_kwargs()
        # ``partial`` serializers still emit declared defaults; drop anything the
        # client did not actually send so PATCH stays a partial update.
        payload = {key: value for key, value in payload.items() if key in request.data
                   or (key == "geofence_type" and "type" in request.data)}
        geofence = services.update_geofence(geofence=geofence, **payload)
        return Response(GeofenceSerializer(geofence).data)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        services.delete_geofence(geofence=self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)
