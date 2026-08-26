"""Read-side queries for accounts."""
from __future__ import annotations

from django.db.models import QuerySet

from accounts.models import User


def get_user_by_email(email: str) -> User | None:
    return User.objects.filter(email=(email or "").strip().lower()).first()


def get_admin() -> User | None:
    """The deployment's single super admin, if one has been created yet."""
    return User.objects.admins().select_related("organization").first()


def organization_members(organization_id: int) -> QuerySet[User]:
    """Active members of one organization, ready for list rendering."""
    return (
        User.objects.filter(organization_id=organization_id, is_active=True)
        .select_related("organization")
        .order_by("name", "email")
    )


def visible_users_for(user) -> QuerySet[User]:
    """Users the caller is allowed to read.

    Regular users only ever see themselves; admins see their organization;
    platform admins see everybody.
    """
    if user.is_platform_admin:
        return User.objects.select_related("organization")
    if user.is_organization_admin and user.organization_id:
        return User.objects.filter(organization_id=user.organization_id).select_related(
            "organization"
        )
    return User.objects.filter(pk=user.pk).select_related("organization")
