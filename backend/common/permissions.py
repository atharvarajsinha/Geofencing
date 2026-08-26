"""Reusable permission classes.

These deliberately depend only on duck-typed properties of the user model
(``is_platform_admin``, ``is_organization_admin``, ``organization_id``) so the
module stays free of app level imports.

Tenancy rule enforced here and in :mod:`common.mixins`:

* a user may only ever see objects belonging to their own organization,
* a platform admin (``SUPER_ADMIN`` without an organization) may cross
  organizations because that role exists to operate the deployment itself.
"""
from __future__ import annotations

from typing import Any

from rest_framework.permissions import BasePermission, SAFE_METHODS
from rest_framework.request import Request
from rest_framework.views import APIView


def _is_authenticated(request: Request) -> bool:
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and user.is_active)


class IsOrganizationMember(BasePermission):
    """Authenticated and attached to an active organization."""

    message = "Your account is not attached to an active organization."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not _is_authenticated(request):
            return False
        user = request.user
        if user.is_platform_admin:
            return True
        return bool(user.organization_id and user.organization.is_active)


class IsOrganizationAdmin(BasePermission):
    """Organization ``ADMIN`` (or platform ``SUPER_ADMIN``)."""

    message = "Administrator role required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return _is_authenticated(request) and request.user.is_organization_admin


class IsPlatformAdmin(BasePermission):
    """Deployment-wide super administrator."""

    message = "Platform administrator role required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return _is_authenticated(request) and request.user.is_platform_admin


class ReadOnlyForMembersAdminForWrites(BasePermission):
    """Members may read; only organization admins may write."""

    message = "Administrator role required to modify this resource."

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not _is_authenticated(request):
            return False
        if request.method in SAFE_METHODS:
            return IsOrganizationMember().has_permission(request, view)
        return request.user.is_organization_admin


class BelongsToSameOrganization(BasePermission):
    """Object level tenancy check.

    Querysets are already scoped (see :class:`common.mixins.OrganizationScopedMixin`);
    this is the second, independent line of defence for objects that are looked
    up outside of a scoped queryset.
    """

    message = "This object belongs to another organization."

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        user = request.user
        if user.is_platform_admin:
            return True
        organization_id = getattr(obj, "organization_id", None)
        if organization_id is None:
            organization_id = getattr(getattr(obj, "organization", None), "id", None)
        return organization_id is not None and organization_id == user.organization_id
