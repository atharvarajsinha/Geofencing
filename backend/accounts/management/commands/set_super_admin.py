"""Point the single super admin role at one account.

    python manage.py set_super_admin admin@example.com

Promotes that account and demotes whoever held the role, in one transaction.
Everybody else stays -- or becomes -- a regular ``USER``.
"""
from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts import selectors, services
from accounts.enums import UserRole
from accounts.models import User
from common.exceptions import ValidationFailed


class Command(BaseCommand):
    help = "Make one account the deployment's single super admin."

    def add_arguments(self, parser) -> None:
        parser.add_argument("email", help="Email address of the account to promote.")
        parser.add_argument(
            "--demote-others",
            action="store_true",
            help=(
                "Also reset every other non-admin account to the USER role "
                "(useful after importing data from a multi-admin deployment)."
            ),
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        email = options["email"].strip().lower()
        user = selectors.get_user_by_email(email)
        if user is None:
            raise CommandError(f"No account with email {email!r}.")

        previous = selectors.get_admin()
        try:
            services.transfer_admin(to_user=user)
        except ValidationFailed as exc:
            raise CommandError(str(exc)) from exc

        if options["demote_others"]:
            demoted = (
                User.objects.exclude(pk=user.pk)
                .exclude(role=UserRole.USER)
                .update(role=UserRole.USER)
            )
            self.stdout.write(f"Reset {demoted} other account(s) to USER.")

        if previous is not None and previous.pk != user.pk:
            self.stdout.write(f"Demoted {previous.email} to USER.")
        self.stdout.write(
            self.style.SUCCESS(f"{user.email} is now the super admin.")
        )
