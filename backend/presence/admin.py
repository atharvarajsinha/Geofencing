from __future__ import annotations

from django.contrib import admin

from presence.models import Presence, PresenceEvent


class PresenceEventInline(admin.TabularInline):
    model = PresenceEvent
    extra = 0
    fields = ("event_type", "reason", "previous_status", "new_status", "timestamp")
    readonly_fields = fields
    can_delete = False
    ordering = ("-timestamp",)


@admin.register(Presence)
class PresenceAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "user",
        "geofence",
        "status",
        "check_in_at",
        "check_out_at",
        "last_seen_at",
    )
    list_filter = ("status", "organization", "geofence", "date")
    search_fields = ("user__email", "user__name")
    date_hierarchy = "date"
    inlines = (PresenceEventInline,)
    readonly_fields = (
        "user",
        "organization",
        "geofence",
        "date",
        "consecutive_inside",
        "consecutive_outside",
        "last_reading_at",
        "last_verdict",
        "last_distance_m",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request) -> bool:
        # Presence is derived state: it is produced by the state machine only.
        return False


@admin.register(PresenceEvent)
class PresenceEventAdmin(admin.ModelAdmin):
    list_display = (
        "timestamp",
        "user",
        "geofence",
        "event_type",
        "reason",
        "previous_status",
        "new_status",
    )
    list_filter = ("event_type", "reason", "organization", "geofence")
    search_fields = ("user__email", "user__name")
    date_hierarchy = "timestamp"
    readonly_fields = tuple(field.name for field in PresenceEvent._meta.fields)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        # Append-only audit trail.
        return False
