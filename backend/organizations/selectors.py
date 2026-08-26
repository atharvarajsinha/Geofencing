"""Read-side queries for organizations."""
from __future__ import annotations

from django.db.models import QuerySet

from organizations.models import Organization


def active_organizations() -> QuerySet[Organization]:
    return Organization.objects.filter(is_active=True)


def get_organization(organization_id: int) -> Organization | None:
    return Organization.objects.filter(pk=organization_id).first()


def visible_organizations_for(user) -> QuerySet[Organization]:
    """Organizations the caller is allowed to see.

    A platform admin sees every tenant; anybody else sees only their own.
    """
    if user.is_platform_admin:
        return Organization.objects.all()
    if not user.organization_id:
        return Organization.objects.none()
    return Organization.objects.filter(pk=user.organization_id)
