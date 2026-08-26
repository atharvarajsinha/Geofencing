"""Report whether the geofence table matches the PostGIS-free schema.

    python manage.py check_geofence_schema

Read-only. Exists because the geofence migrations were rewritten in place: a
database created before that change already has ``0001_initial`` recorded, so
``migrate`` reports "No migrations to apply" while the table still has the old
geometry columns. The first request that touches a geofence then fails with
``column "center_latitude" does not exist``.

Exits 0 when the schema is current, 1 when it needs converting, so it can gate
a deploy.
"""
from __future__ import annotations

import sys
from typing import Any

from django.core.management.base import BaseCommand
from django.db import connection

REQUIRED_COLUMNS = (
    "center_latitude",
    "center_longitude",
    "min_latitude",
    "max_latitude",
    "min_longitude",
    "max_longitude",
)
REMOVED_COLUMNS = ("center_point", "geometry")


def _columns(table: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s
            """,
            [table],
        )
        return {row[0] for row in cursor.fetchall()}


class Command(BaseCommand):
    help = "Verify the geofence table has the float-column schema (no PostGIS)."

    def handle(self, *args: Any, **options: Any) -> None:
        columns = _columns("geofences_geofence")
        if not columns:
            self.stdout.write(
                self.style.ERROR(
                    "Table geofences_geofence does not exist. Run 'manage.py migrate'."
                )
            )
            sys.exit(1)

        missing = [name for name in REQUIRED_COLUMNS if name not in columns]
        leftover = [name for name in REMOVED_COLUMNS if name in columns]
        location_columns = _columns("locations_locationupdate")
        stale_point = "point" in location_columns

        if not missing and not leftover and not stale_point:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT geofence_type, count(*) FROM geofences_geofence GROUP BY 1"
                )
                counts = ", ".join(f"{kind}={total}" for kind, total in cursor.fetchall())
            self.stdout.write(
                self.style.SUCCESS(
                    f"Schema is current. Geofences: {counts or 'none'}."
                )
            )
            return

        self.stdout.write(self.style.ERROR("Schema is OUT OF DATE."))
        if missing:
            self.stdout.write(f"  missing columns : {', '.join(missing)}")
        if leftover:
            self.stdout.write(f"  leftover geometry columns: {', '.join(leftover)}")
        if stale_point:
            self.stdout.write("  leftover column : locations_locationupdate.point")

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM geofences_geofence WHERE geofence_type = 'POLYGON'"
            )
            polygons = cursor.fetchone()[0] if "geofence_type" in columns else 0

        self.stdout.write("")
        self.stdout.write("To convert while keeping your data, run once:")
        self.stdout.write("  psql <your-database-url> -f scripts/migrate_from_postgis.sql")
        if polygons:
            self.stdout.write(
                self.style.WARNING(
                    f"  ({polygons} POLYGON geofence(s) will become their bounding "
                    f"rectangle - review them afterwards.)"
                )
            )
        self.stdout.write("Or, to start clean: drop the database and 'manage.py migrate'.")
        sys.exit(1)
