"""Write-side operations for accounts."""
from __future__ import annotations

from typing import Any

from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from accounts.enums import UserRole
from accounts.models import User
from common.exceptions import ValidationFailed
from organizations.models import Organization

ONE_ADMIN_MESSAGE = (
    "This deployment already has a super admin. Transfer the role instead of "
    "creating a second administrator."
)


def _assert_no_other_admin(*, exclude_pk: int | None = None) -> None:
    """Guard the single-admin invariant with a readable 400.

    ``only_one_admin_account`` would reject a second administrator anyway; this
    turns the database error into an explanation the API can return.
    """
    existing = User.objects.admins()
    if exclude_pk is not None:
        existing = existing.exclude(pk=exclude_pk)
    other = existing.first()
    if other is not None:
        raise ValidationFailed(
            ONE_ADMIN_MESSAGE,
            errors={"role": [f"{other.email} is already the super admin."]},
        )


@transaction.atomic
def create_user(
    *,
    email: str,
    name: str,
    password: str,
    organization: Organization | None,
    role: str = UserRole.USER,
    phone_number: str = "",
    is_active: bool = True,
) -> User:
    """Create an account, enforcing the tenancy and single-admin invariants.

    Only the ``ADMIN`` account may exist without an organization, and only one
    ``ADMIN`` may exist at all.
    """
    if organization is None and role != UserRole.ADMIN:
        raise ValidationFailed(
            "A non platform-admin account must belong to an organization.",
            errors={"organization": ["This field is required for this role."]},
        )
    if role == UserRole.ADMIN:
        _assert_no_other_admin()

    user = User(
        email=email,
        name=name,
        role=role,
        phone_number=phone_number,
        organization=organization,
        is_active=is_active,
    )
    validate_password(password, user)
    user.set_password(password)
    user.full_clean(exclude=["password"])
    user.save()
    return user


@transaction.atomic
def update_user(*, user: User, **fields: Any) -> User:
    allowed = {"name", "phone_number", "role", "is_active"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValidationFailed(
            "Unknown fields.", errors={key: ["Unknown field."] for key in sorted(unknown)}
        )
    if fields.get("role") == UserRole.ADMIN:
        _assert_no_other_admin(exclude_pk=user.pk)
    for field, value in fields.items():
        setattr(user, field, value)
    user.full_clean(exclude=["password"])
    user.save(update_fields=[*fields.keys(), "updated_at"])
    return user


@transaction.atomic
def set_password(*, user: User, raw_password: str) -> User:
    validate_password(raw_password, user)
    user.set_password(raw_password)
    user.save(update_fields=["password", "updated_at"])
    return user


@transaction.atomic
def transfer_admin(*, to_user: User) -> User:
    """Make ``to_user`` the single super admin, demoting the incumbent.

    One transaction, and the demotion happens before the promotion, so the
    ``only_one_admin_account`` constraint is never momentarily violated.
    """
    if to_user.role == UserRole.ADMIN:
        return to_user

    incumbent = User.objects.admins().exclude(pk=to_user.pk).first()
    if incumbent is not None:
        if incumbent.organization_id is None:
            # Demoting it would leave a USER with no organization, which
            # ``user_requires_organization_unless_admin`` forbids.
            raise ValidationFailed(
                "The current super admin is a platform account with no "
                "organization and cannot be demoted to a regular user.",
                errors={
                    "role": [
                        f"Delete or re-home {incumbent.email} before moving the "
                        f"role."
                    ]
                },
            )
        incumbent.role = UserRole.USER
        incumbent.save(update_fields=["role", "updated_at"])

    to_user.role = UserRole.ADMIN
    to_user.full_clean(exclude=["password"])
    to_user.save(update_fields=["role", "updated_at"])
    return to_user
