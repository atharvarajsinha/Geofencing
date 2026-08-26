from __future__ import annotations

from django.contrib import admin

from locations.models import LocationAnomaly, LocationUpdate


class LocationAnomalyInline(admin.TabularInline):
    model = LocationAnomaly
    extra = 0
    readonly_fields = ("anomaly_type", "severity", "details", "created_at")
    can_delete = False


@admin.register(LocationUpdate)
class LocationUpdateAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "latitude",
        "longitude",
        "accuracy",
        "recorded_at",
        "received_at",
        "confidence",
        "is_trusted",
        "is_flagged",
    )
    list_filter = ("is_trusted", "is_flagged", "confidence", "organization")
    search_fields = ("user__email", "user__name", "device_id", "session_id", "client_event_id")
    date_hierarchy = "recorded_at"
    inlines = (LocationAnomalyInline,)
    readonly_fields = tuple(
        field.name for field in LocationUpdate._meta.fields
    )  # history is append-only

    def has_add_permission(self, request) -> bool:
        return False


@admin.register(LocationAnomaly)
class LocationAnomalyAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "anomaly_type", "severity", "created_at")
    list_filter = ("anomaly_type", "severity", "organization")
    search_fields = ("user__email", "user__name")
    date_hierarchy = "created_at"
    readonly_fields = ("user", "organization", "location_update", "anomaly_type", "severity", "details", "created_at")

    def has_add_permission(self, request) -> bool:
        return False
