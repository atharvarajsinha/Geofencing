"""View mixins shared by the API layer."""
from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

from common.exceptions import PermissionDenied


class OrganizationScopedMixin:
    """Restrict every queryset of a view to the caller's organization.

    Views must define :attr:`organization_field` when the tenancy column is not
    called ``organization``. A platform admin bypasses the filter and may
    optionally narrow the result set with ``?organization=<id>``.
    """

    organization_field: str = "organization"

    def get_queryset(self) -> QuerySet[Any]:
        queryset = super().get_queryset()  # type: ignore[misc]
        return self.scope_queryset_to_organization(queryset)

    def scope_queryset_to_organization(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        user = self.request.user  # type: ignore[attr-defined]

        if user.is_platform_admin:
            requested = self.request.query_params.get("organization")  # type: ignore[attr-defined]
            if requested:
                return queryset.filter(**{f"{self.organization_field}_id": requested})
            return queryset

        if not user.organization_id:
            # Defensive: IsOrganizationMember should already have rejected this.
            raise PermissionDenied("Your account is not attached to an organization.")

        return queryset.filter(**{f"{self.organization_field}_id": user.organization_id})

    @property
    def effective_organization_id(self) -> int | None:
        """Organization the request operates on (``None`` for platform-wide)."""
        user = self.request.user  # type: ignore[attr-defined]
        if user.is_platform_admin:
            requested = self.request.query_params.get("organization")  # type: ignore[attr-defined]
            return int(requested) if requested else None
        return user.organization_id


class SerializerContextMixin:
    """Always give serializers access to the request and the caller."""

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()  # type: ignore[misc]
        request = context.get("request")
        context["user"] = getattr(request, "user", None)
        context["organization_id"] = getattr(
            getattr(request, "user", None), "organization_id", None
        )
        return context
