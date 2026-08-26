"""Custom user model: email is the username."""
from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from accounts.enums import UserRole
from accounts.managers import UserManager

PHONE_VALIDATOR = RegexValidator(
    regex=r"^\+?[0-9]{7,20}$",
    message="Phone number must be 7-20 digits, optionally prefixed with '+'.",
)


class User(AbstractBaseUser, PermissionsMixin):
    """A person who either monitors presence (the admin) or is tracked (a user).

    There is exactly one ``ADMIN`` account in the deployment -- the super admin.
    ``only_one_admin_account`` makes that a database fact rather than a
    convention, so a second administrator cannot appear through a management
    command, a shell session or a race between two requests.
    """

    email = models.EmailField(max_length=254, unique=True, db_index=True)
    name = models.CharField(max_length=150)
    phone_number = models.CharField(
        max_length=20, blank=True, default="", validators=[PHONE_VALIDATOR]
    )
    role = models.CharField(
        max_length=16, choices=UserRole.choices, default=UserRole.USER, db_index=True
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="users",
        null=True,
        blank=True,
        help_text=(
            "Null only for the platform level ADMIN account that operates the "
            "deployment itself."
        ),
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(
        default=False, help_text="Grants access to the Django admin site."
    )
    date_joined = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        db_table = "accounts_user"
        ordering = ("name", "email")
        indexes = [
            models.Index(fields=["organization", "is_active"], name="user_org_active_idx"),
            models.Index(fields=["organization", "role"], name="user_org_role_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(organization__isnull=False)
                | models.Q(role=UserRole.ADMIN),
                name="user_requires_organization_unless_admin",
            ),
            # A partial unique index over a single-valued column: at most one
            # row may carry role='ADMIN', deployment wide.
            models.UniqueConstraint(
                fields=["role"],
                condition=models.Q(role=UserRole.ADMIN),
                name="only_one_admin_account",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>"

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        return super().save(*args, **kwargs)

    # -- Authorisation helpers -------------------------------------------
    @property
    def is_admin(self) -> bool:
        """The single super admin of this deployment."""
        return self.role == UserRole.ADMIN

    @property
    def is_platform_admin(self) -> bool:
        """Deployment operator: the only account allowed to cross tenants."""
        return self.is_admin and self.organization_id is None

    @property
    def is_organization_admin(self) -> bool:
        """May manage geofences and read every member's presence."""
        return self.role in UserRole.admin_roles()

    @property
    def is_tracked_user(self) -> bool:
        """Submits location updates for themselves."""
        return self.organization_id is not None

    def get_short_name(self) -> str:
        return self.name.split(" ")[0] if self.name else self.email

    def get_full_name(self) -> str:
        return self.name or self.email
