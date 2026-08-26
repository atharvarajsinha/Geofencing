"""Account specific permissions.

Re-exports the shared tenancy permissions so views can import everything they
need from one place.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from common.permissions import (  # noqa: F401  (re-exported for convenience)
    BelongsToSameOrganization,
    IsOrganizationAdmin,
    IsOrganizationMember,
    IsPlatformAdmin,
    ReadOnlyForMembersAdminForWrites,
)


class IsSelfOrOrganizationAdmin(BasePermission):
    """Own record, or any record inside the admin's organization."""

    message = "You may only access your own account."

    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        user = request.user
        if obj.pk == user.pk:
            return True
        if user.is_platform_admin:
            return True
        return bool(
            user.is_organization_admin
            and user.organization_id
            and obj.organization_id == user.organization_id
        )
