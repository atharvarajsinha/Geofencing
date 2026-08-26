from __future__ import annotations

from django.contrib import admin

from geofences.models import Geofence


@admin.register(Geofence)
class GeofenceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "organization",
        "geofence_type",
        "radius",
        "entry_radius",
        "exit_radius",
        "is_active",
    )
    list_filter = ("geofence_type", "is_active", "organization")
    search_fields = ("name", "organization__name", "organization__code")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("organization", "name", "geofence_type", "is_active")}),
        ("Circle", {"fields": ("center_latitude", "center_longitude", "radius")}),
        (
            "Bounding box",
            {
                "fields": (
                    "min_latitude",
                    "max_latitude",
                    "min_longitude",
                    "max_longitude",
                ),
                "description": (
                    "The shape itself for a RECTANGLE. For a CIRCLE these are "
                    "recomputed from the centre and radius on save."
                ),
            },
        ),
        (
            "Hysteresis and debouncing",
            {
                "fields": (
                    "entry_radius",
                    "exit_radius",
                    "required_inside_readings",
                    "required_outside_readings",
                    "stale_after_seconds",
                )
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
