"""Account level enumerations."""
from __future__ import annotations

from django.db import models


class UserRole(models.TextChoices):
    """Authorisation roles.

    The deployment has exactly **one** ``ADMIN`` account -- the super admin --
    enforced by a unique constraint on :class:`accounts.models.User`. Everybody
    else is a ``USER``: somebody whose presence is tracked.

    An ``ADMIN`` without an organization is the platform operator and is the
    only account allowed to cross tenant boundaries. An ``ADMIN`` attached to an
    organization is the owner of that single tenant.
    """

    ADMIN = "ADMIN", "Super administrator"
    USER = "USER", "User"

    @classmethod
    def admin_roles(cls) -> tuple[str, ...]:
        return (cls.ADMIN.value,)
