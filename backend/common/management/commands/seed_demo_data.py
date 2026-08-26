"""Create a small, realistic dataset for manual testing and demos.

    python manage.py seed_demo_data --reset

Never run this against production data: ``--reset`` deletes the demo tenant.
"""
from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.enums import UserRole
from accounts.models import User
from accounts.services import create_user
from geofences.enums import GeofenceType
from geofences.services import create_geofence
from organizations.models import Organization
from organizations.services import create_organization

DEMO_CODE = "DEMO"
DEMO_PASSWORD = "DemoPassw0rd!2026"

CAMPUS_LATITUDE = 29.5976
CAMPUS_LONGITUDE = 79.6591

#: A ~130 m x ~190 m box over the academic block.
ACADEMIC_BLOCK_BOX = {
    "min_latitude": 29.5971,
    "max_latitude": 29.5983,
    "min_longitude": 79.6581,
    "max_longitude": 79.6601,
}


class Command(BaseCommand):
    help = "Seed a demo organization with the super admin, members and two geofences."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete the existing demo organization first.",
        )
        parser.add_argument("--members", type=int, default=5)

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        if options["reset"]:
            deleted = Organization.objects.filter(code=DEMO_CODE).delete()
            self.stdout.write(f"Removed previous demo data: {deleted}")

        if Organization.objects.filter(code=DEMO_CODE).exists():
            raise CommandError(
                "Demo data already exists. Re-run with --reset to recreate it."
            )

        organization = create_organization(
            name="Demo University", code=DEMO_CODE, timezone_name="Asia/Kolkata"
        )

        # One super admin per deployment (``only_one_admin_account``). Reuse the
        # existing one if this is a re-seed after ``--reset`` left it behind.
        admin = User.objects.admins().first()
        if admin is None:
            admin = create_user(
                email="admin@demo.test",
                name="Demo Super Admin",
                password=DEMO_PASSWORD,
                organization=organization,
                role=UserRole.ADMIN,
            )

        members = [
            create_user(
                email=f"member{index}@demo.test",
                name=f"Demo Member {index}",
                password=DEMO_PASSWORD,
                organization=organization,
                role=UserRole.USER,
            )
            for index in range(1, options["members"] + 1)
        ]

        circle = create_geofence(
            organization=organization,
            name="Campus (circle)",
            geofence_type=GeofenceType.CIRCLE,
            latitude=CAMPUS_LATITUDE,
            longitude=CAMPUS_LONGITUDE,
            radius=150,
        )
        rectangle = create_geofence(
            organization=organization,
            name="Academic Block (rectangle)",
            geofence_type=GeofenceType.RECTANGLE,
            **ACADEMIC_BLOCK_BOX,
        )

        self.stdout.write(self.style.SUCCESS("Demo data created."))
        self.stdout.write(f"  organization : {organization.code} ({organization.timezone})")
        self.stdout.write(f"  super admin  : {admin.email} / {DEMO_PASSWORD}")
        self.stdout.write(f"  members      : {len(members)} (memberN@demo.test)")
        self.stdout.write(
            f"  geofences    : #{circle.pk} circle, #{rectangle.pk} rectangle"
        )
        self.stdout.write(
            f"  test a fix   : POST /api/location/update/ "
            f'{{"latitude": {CAMPUS_LATITUDE}, "longitude": {CAMPUS_LONGITUDE}, '
            f'"accuracy": 12, "recorded_at": "<now in ISO 8601>"}}'
        )
