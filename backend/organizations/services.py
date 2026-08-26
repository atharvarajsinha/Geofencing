"""Write-side operations for organizations."""
from __future__ import annotations

from typing import Any

from django.db import transaction

from organizations.models import Organization


@transaction.atomic
def create_organization(
    *, name: str, code: str, timezone_name: str = "UTC", is_active: bool = True
) -> Organization:
    organization = Organization(
        name=name, code=code, timezone=timezone_name, is_active=is_active
    )
    organization.full_clean()
    organization.save()
    return organization


@transaction.atomic
def update_organization(*, organization: Organization, **fields: Any) -> Organization:
    allowed = {"name", "code", "timezone", "is_active"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"Cannot update unknown organization fields: {sorted(unknown)}")

    for field, value in fields.items():
        setattr(organization, field, value)
    organization.full_clean()
    organization.save(update_fields=[*fields.keys(), "updated_at"])
    return organization
