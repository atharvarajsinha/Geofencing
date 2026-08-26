"""Create the deployment's super admin if it does not exist yet.

Intended for a container start command or a Render pre-deploy hook::

    python manage.py ensure_superuser

Reads the same environment variables Django's own ``createsuperuser --noinput``
uses, so nothing new has to be configured:

===============================  ==========================================
``DJANGO_SUPERUSER_EMAIL``       required - the login (this project has no
                                 ``username`` field; email is USERNAME_FIELD)
``DJANGO_SUPERUSER_PASSWORD``    required
``DJANGO_SUPERUSER_NAME``        optional - display name, defaults to the
                                 local part of the email
===============================  ==========================================

Why not plain ``createsuperuser --noinput``: it fails once the account exists,
which turns every redeploy into a failed deploy. This command is idempotent -
it reports what it found and exits 0 - so it is safe to run on every boot.

It also respects the deployment-wide single-``ADMIN`` constraint: it never tries
to create a second one. Use ``set_super_admin`` to move the role between
accounts.
"""
from __future__ import annotations

import os
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.enums import UserRole
from accounts.models import User


class Command(BaseCommand):
    help = "Create the super admin from environment variables, if absent."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--email",
            default=None,
            help="Overrides DJANGO_SUPERUSER_EMAIL.",
        )
        parser.add_argument(
            "--name",
            default=None,
            help="Overrides DJANGO_SUPERUSER_NAME.",
        )
        parser.add_argument(
            "--skip-if-unset",
            action="store_true",
            help=(
                "Exit quietly instead of failing when the credentials are not "
                "configured. Use in a shared start command where the superuser "
                "is provisioned some other way."
            ),
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        email = (options["email"] or os.environ.get("DJANGO_SUPERUSER_EMAIL") or "").strip().lower()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD") or ""
        name = (
            options["name"]
            or os.environ.get("DJANGO_SUPERUSER_NAME")
            or (email.split("@")[0] if email else "")
        ).strip()

        if not email or not password:
            missing = [
                variable
                for variable, value in (
                    ("DJANGO_SUPERUSER_EMAIL", email),
                    ("DJANGO_SUPERUSER_PASSWORD", password),
                )
                if not value
            ]
            message = f"Missing {' and '.join(missing)}."
            if options["skip_if_unset"]:
                self.stdout.write(self.style.WARNING(f"{message} Skipping."))
                return
            raise CommandError(
                f"{message} Set them in the environment, or pass --skip-if-unset "
                f"to make this a no-op."
            )

        # An ADMIN is unique deployment-wide, so check the role before the email.
        existing_admin = User.objects.admins().first()
        if existing_admin is not None:
            if existing_admin.email == email:
                self.stdout.write(
                    self.style.SUCCESS(f"Super admin {email} already exists; nothing to do.")
                )
            else:
                # Not an error: the deployment has its admin, just not this one.
                self.stdout.write(
                    self.style.WARNING(
                        f"A super admin already exists ({existing_admin.email}), so "
                        f"{email} was not created. Run "
                        f"'manage.py set_super_admin {email}' to move the role."
                    )
                )
            return

        if User.objects.filter(email=email).exists():
            self.stdout.write(
                self.style.WARNING(
                    f"An account with {email} exists but is not the super admin. Run "
                    f"'manage.py set_super_admin {email}' to promote it."
                )
            )
            return

        try:
            User.objects.create_superuser(
                email=email,
                password=password,
                name=name,
                role=UserRole.ADMIN,
            )
        except ValidationError as exc:
            # full_clean() in the manager; surface the field errors readably.
            raise CommandError(f"Could not create the super admin: {exc}") from exc

        # Never echo the password, not even at debug level.
        self.stdout.write(self.style.SUCCESS(f"Created super admin {email}."))
