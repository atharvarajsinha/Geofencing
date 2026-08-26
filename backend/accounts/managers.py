"""Manager for the custom user model."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib.auth.base_user import BaseUserManager
from django.db import models

from accounts.enums import UserRole

if TYPE_CHECKING:  # pragma: no cover
    from accounts.models import User


class UserQuerySet(models.QuerySet):
    def active(self) -> "UserQuerySet":
        return self.filter(is_active=True)

    def in_organization(self, organization_id: int) -> "UserQuerySet":
        return self.filter(organization_id=organization_id)

    def with_role(self, *roles: str) -> "UserQuerySet":
        return self.filter(role__in=roles)

    def admins(self) -> "UserQuerySet":
        """The super admin. At most one row, by database constraint."""
        return self.filter(role=UserRole.ADMIN)


class UserManager(BaseUserManager):
    """Email based user manager."""

    use_in_migrations = True

    def get_queryset(self) -> UserQuerySet:
        return UserQuerySet(self.model, using=self._db)

    def active(self) -> UserQuerySet:
        return self.get_queryset().active()

    def admins(self) -> UserQuerySet:
        return self.get_queryset().admins()

    def normalize_email(self, email: str | None) -> str:
        return super().normalize_email((email or "").strip()).lower()

    def _create_user(self, email: str, password: str | None, **extra: Any) -> "User":
        if not email:
            raise ValueError("Users must have an email address.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> "User":
        extra.setdefault("role", UserRole.USER)
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> "User":
        """Create the single super admin.

        ``createsuperuser`` fails if one already exists: the ``ADMIN`` role is
        unique, and ``full_clean`` checks that before touching the database.
        """
        extra.setdefault("role", UserRole.ADMIN)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_active", True)
        if extra["is_staff"] is not True or extra["is_superuser"] is not True:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True.")
        return self._create_user(email, password, **extra)
