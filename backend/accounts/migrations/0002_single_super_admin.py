"""Collapse the role model onto a single super admin.

``SUPER_ADMIN`` and ``ADMIN`` were two ways of saying "administrator": one
platform wide, one per organization. This migration merges them into a single
``ADMIN`` role and makes it unique, so the deployment has exactly one super
admin and every other account is a regular ``USER``.

Existing rows are collapsed rather than rejected:

* every ``SUPER_ADMIN`` becomes ``ADMIN``;
* if that leaves more than one administrator, the platform account (no
  organization) wins, otherwise the oldest one does, and the rest are demoted
  to ``USER``.

The data migration must run *before* the unique constraint is added, which is
why the operations are ordered the way they are.
"""
from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


def collapse_to_one_admin(apps, schema_editor) -> None:
    User = apps.get_model("accounts", "User")

    User.objects.filter(role="SUPER_ADMIN").update(role="ADMIN")

    admins = list(
        User.objects.filter(role="ADMIN").order_by("organization_id", "pk")
    )
    if len(admins) <= 1:
        return

    # ``order_by("organization_id", ...)`` puts NULL first on PostgreSQL only
    # with NULLS FIRST, so pick the platform account explicitly.
    keeper = next((row for row in admins if row.organization_id is None), None)
    if keeper is None:
        keeper = min(admins, key=lambda row: row.pk)

    User.objects.filter(role="ADMIN").exclude(pk=keeper.pk).update(role="USER")


def split_admin_role(apps, schema_editor) -> None:
    """Reverse: the surviving administrator becomes a ``SUPER_ADMIN`` again."""
    User = apps.get_model("accounts", "User")
    User.objects.filter(role="ADMIN", organization__isnull=True).update(
        role="SUPER_ADMIN"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="user",
            name="user_requires_organization_unless_super_admin",
        ),
        migrations.RunPython(collapse_to_one_admin, split_admin_role),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[("ADMIN", "Super administrator"), ("USER", "User")],
                db_index=True,
                default="USER",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Null only for the platform level ADMIN account that "
                    "operates the deployment itself."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="users",
                to="organizations.organization",
            ),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.CheckConstraint(
                condition=models.Q(("organization__isnull", False), ("role", "ADMIN"), _connector="OR"),
                name="user_requires_organization_unless_admin",
            ),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                condition=models.Q(("role", "ADMIN")),
                fields=("role",),
                name="only_one_admin_account",
            ),
        ),
    ]
