"""Organization: the tenancy root of the whole system.

Every other row in the database (users, geofences, locations, presence) carries
an ``organization_id`` so that isolation can be enforced with a single filter
instead of a join chain.
"""
from __future__ import annotations

from django.core.validators import MinLengthValidator, RegexValidator
from django.db import models

CODE_VALIDATOR = RegexValidator(
    regex=r"^[A-Z0-9][A-Z0-9_-]{1,31}$",
    message=(
        "Code must be 2-32 characters of uppercase letters, digits, hyphen or "
        "underscore, and must not start with a separator."
    ),
)


class Organization(models.Model):
    """A tenant: a college, company or campus operator."""

    name = models.CharField(max_length=200, validators=[MinLengthValidator(2)])
    code = models.CharField(
        max_length=32,
        unique=True,
        validators=[CODE_VALIDATOR],
        help_text="Short stable identifier used by integrations, e.g. SITARE.",
    )
    timezone = models.CharField(
        max_length=64,
        default="UTC",
        help_text=(
            "IANA timezone used to decide which calendar day an attendance "
            "record belongs to."
        ),
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "organizations_organization"
        ordering = ("name",)
        indexes = [
            models.Index(fields=["is_active"], name="org_is_active_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        return super().save(*args, **kwargs)
