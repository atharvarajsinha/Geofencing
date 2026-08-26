"""Presence state and its audit trail.

``Presence`` is one row per (user, geofence, attendance day) and holds the
current state of the machine. ``PresenceEvent`` is append-only history: every
row corresponds to an actual transition, never to a mere GPS reading, which is
what keeps repeated readings from producing duplicate ENTERED/EXITED events.
"""
from __future__ import annotations

from django.db import models

from geofences.enums import ContainmentVerdict
from presence.enums import PresenceEventType, PresenceStatus, TransitionReason


class PresenceQuerySet(models.QuerySet):
    def for_organization(self, organization_id: int) -> "PresenceQuerySet":
        return self.filter(organization_id=organization_id)

    def for_user(self, user_id: int) -> "PresenceQuerySet":
        return self.filter(user_id=user_id)

    def on_date(self, day) -> "PresenceQuerySet":
        return self.filter(date=day)

    def open(self) -> "PresenceQuerySet":
        return self.filter(status__in=PresenceStatus.open_statuses())

    def with_related(self) -> "PresenceQuerySet":
        return self.select_related("user", "geofence", "organization")


class Presence(models.Model):
    """Current presence state of one user in one geofence on one day."""

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="presences"
    )
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="presences"
    )
    geofence = models.ForeignKey(
        "geofences.Geofence", on_delete=models.PROTECT, related_name="presences"
    )
    date = models.DateField(
        help_text="Attendance day in the organization's timezone, derived from recorded_at."
    )

    status = models.CharField(
        max_length=16, choices=PresenceStatus.choices, default=PresenceStatus.UNKNOWN
    )

    check_in_at = models.DateTimeField(
        null=True, blank=True, help_text="First ENTERED of the day (device time)."
    )
    check_out_at = models.DateTimeField(
        null=True, blank=True, help_text="Most recent EXITED of the day (device time)."
    )
    last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="recorded_at of the most recent trusted fix that reached this row.",
    )
    stale_since = models.DateTimeField(
        null=True, blank=True, help_text="Server time the row was marked STALE."
    )

    last_latitude = models.FloatField(null=True, blank=True)
    last_longitude = models.FloatField(null=True, blank=True)
    last_accuracy = models.FloatField(null=True, blank=True)
    last_distance_m = models.FloatField(
        null=True,
        blank=True,
        help_text="Signed distance to the boundary at the last reading; negative inside.",
    )
    last_verdict = models.CharField(
        max_length=16, choices=ContainmentVerdict.choices, blank=True, default=""
    )
    last_reading_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Device time of the last reading applied to this row. Used to reject "
            "out-of-order deliveries and to reset stale streaks."
        ),
    )

    # -- Hysteresis counters ---------------------------------------------
    consecutive_inside = models.PositiveSmallIntegerField(default=0)
    consecutive_outside = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PresenceQuerySet.as_manager()

    class Meta:
        db_table = "presence_presence"
        ordering = ("-date", "user_id")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "geofence", "date"],
                name="presence_unique_user_geofence_day",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "date", "status"], name="presence_org_day_idx"),
            models.Index(fields=["user", "-date"], name="presence_user_day_idx"),
            models.Index(fields=["status", "last_seen_at"], name="presence_status_seen_idx"),
            models.Index(fields=["geofence", "date"], name="presence_geofence_day_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} @ {self.geofence_id} on {self.date}: {self.status}"

    @property
    def is_open(self) -> bool:
        return self.status in PresenceStatus.open_statuses()


class PresenceEventQuerySet(models.QuerySet):
    def for_organization(self, organization_id: int) -> "PresenceEventQuerySet":
        return self.filter(organization_id=organization_id)

    def with_related(self) -> "PresenceEventQuerySet":
        return self.select_related("user", "geofence")


class PresenceEvent(models.Model):
    """An immutable record of one presence transition."""

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="presence_events"
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="presence_events",
    )
    geofence = models.ForeignKey(
        "geofences.Geofence", on_delete=models.PROTECT, related_name="presence_events"
    )
    presence = models.ForeignKey(
        Presence, on_delete=models.CASCADE, related_name="events", null=True, blank=True
    )
    location_update = models.ForeignKey(
        "locations.LocationUpdate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="presence_events",
        help_text="The fix that triggered the transition, when there was one.",
    )

    event_type = models.CharField(max_length=24, choices=PresenceEventType.choices)
    reason = models.CharField(
        max_length=24, choices=TransitionReason.choices, blank=True, default=""
    )
    previous_status = models.CharField(
        max_length=16, choices=PresenceStatus.choices, blank=True, default=""
    )
    new_status = models.CharField(
        max_length=16, choices=PresenceStatus.choices, blank=True, default=""
    )

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    accuracy = models.FloatField(null=True, blank=True)

    timestamp = models.DateTimeField(
        help_text=(
            "When the transition happened: device time for reading-driven events, "
            "server time for timeout-driven events."
        )
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = PresenceEventQuerySet.as_manager()

    class Meta:
        db_table = "presence_presenceevent"
        ordering = ("-timestamp", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=["presence", "event_type", "timestamp"],
                name="presence_event_unique_transition",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-timestamp"], name="event_user_ts_idx"),
            models.Index(fields=["organization", "-timestamp"], name="event_org_ts_idx"),
            models.Index(fields=["geofence", "event_type"], name="event_geofence_type_idx"),
            models.Index(fields=["event_type", "-timestamp"], name="event_type_ts_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} user={self.user_id} at {self.timestamp:%Y-%m-%d %H:%M:%S}"
