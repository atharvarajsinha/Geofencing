"""Organization API.

Tenant administration is a platform-admin concern; regular members may only
read their own organization (the PWA needs its name and timezone).
"""
from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from common.exceptions import NotFound
from common.permissions import IsOrganizationMember, IsPlatformAdmin
from organizations import selectors, services
from organizations.models import Organization
from organizations.serializers import (
    OrganizationSerializer,
    OrganizationWriteSerializer,
)


@extend_schema(tags=["organizations"])
class OrganizationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = OrganizationSerializer
    queryset = Organization.objects.all()
    throttle_scope = "read"

    def get_permissions(self):
        if self.action in {"create", "partial_update", "update"}:
            return [IsPlatformAdmin()]
        return [IsOrganizationMember()]

    def get_queryset(self):
        return selectors.visible_organizations_for(self.request.user)

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """The caller's own organization."""
        if not request.user.organization_id:
            raise NotFound("Your account is not attached to an organization.")
        serializer = self.get_serializer(request.user.organization)
        return Response(serializer.data)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = OrganizationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = services.create_organization(
            name=serializer.validated_data["name"],
            code=serializer.validated_data["code"],
            timezone_name=serializer.validated_data.get("timezone", "UTC"),
            is_active=serializer.validated_data.get("is_active", True),
        )
        return Response(
            OrganizationSerializer(organization).data, status=status.HTTP_201_CREATED
        )

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        organization = self.get_object()
        serializer = OrganizationWriteSerializer(
            organization, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)
        if "timezone" in fields:
            fields["timezone"] = fields.pop("timezone")
        organization = services.update_organization(organization=organization, **fields)
        return Response(OrganizationSerializer(organization).data)
