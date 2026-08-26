"""Raw GPS observations and the anomalies detected on them.

``recorded_at`` (when the device took the fix) and ``received_at`` (when the
server stored it) are kept strictly apart. A PWA that was offline for ten
minutes will POST ten-minute-old fixes; they are perfectly valid history but
they are *not* the user's current position, and only ``recorded_at`` is ever
used for presence decisions.
"""
from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from geofences.enums import ReadingConfidence
from locations.enums import AnomalySeverity, AnomalyType


class LocationUpdateQuerySet(models.QuerySet):
    def for_user(self, user_id: int) -> "LocationUpdateQuerySet":
        return self.filter(user_id=user_id)

    def trusted(self) -> "LocationUpdateQuerySet":
        return self.filter(is_trusted=True)

    def newest_first(self) -> "LocationUpdateQuerySet":
        return self.order_by("-recorded_at", "-id")


class LocationUpdate(models.Model):
    """One GPS fix reported by a device."""

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="location_updates"
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="location_updates",
    )

    latitude = models.FloatField(
        validators=[MinValueValidator(-90.0), MaxValueValidator(90.0)]
    )
    longitude = models.FloatField(
        validators=[MinValueValidator(-180.0), MaxValueValidator(180.0)]
    )

    accuracy = models.FloatField(
        validators=[MinValueValidator(0.0)],
        help_text="Radius of 68% confidence in metres, as reported by the browser.",
    )
    speed = models.FloatField(null=True, blank=True, help_text="Metres per second.")
    heading = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(360.0)],
        help_text="Degrees clockwise from true north.",
    )
    altitude = models.FloatField(null=True, blank=True, help_text="Metres above WGS84.")

    recorded_at = models.DateTimeField(help_text="Device clock time of the fix.")
    received_at = models.DateTimeField(
        auto_now_add=True, help_text="Server time the fix was accepted."
    )

    device_id = models.CharField(max_length=64, blank=True, default="")
    session_id = models.CharField(max_length=64, blank=True, default="")
    client_event_id = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text=(
            "Client generated idempotency key. Re-POSTing the same key returns "
            "the original result instead of creating a duplicate."
        ),
    )

    confidence = models.CharField(
        max_length=8,
        choices=ReadingConfidence.choices,
        default=ReadingConfidence.HIGH,
        help_text="HIGH when accuracy is within MAX_ACCEPTABLE_ACCURACY_M.",
    )
    is_trusted = models.BooleanField(
        default=True,
        help_text=(
            "False when a HIGH severity anomaly was detected. Untrusted fixes are "
            "stored for the audit trail but never drive presence transitions."
        ),
    )
    is_flagged = models.BooleanField(
        default=False, help_text="At least one anomaly was recorded for this fix."
    )
    processed_at = models.DateTimeField(null=True, blank=True)

    objects = LocationUpdateQuerySet.as_manager()

    class Meta:
        db_table = "locations_locationupdate"
        ordering = ("-recorded_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "client_event_id"],
                condition=models.Q(client_event_id__isnull=False),
                name="location_unique_client_event_per_user",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-recorded_at"], name="locupd_user_recorded_idx"),
            models.Index(
                fields=["organization", "-recorded_at"], name="locupd_org_recorded_idx"
            ),
            models.Index(fields=["-received_at"], name="locupd_received_idx"),
            models.Index(
                fields=["organization", "is_flagged"], name="locupd_org_flagged_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} @ {self.latitude:.5f},{self.longitude:.5f} ({self.recorded_at:%Y-%m-%d %H:%M:%S})"

    @property
    def delay_seconds(self) -> float:
        """How long the fix took to reach the server (network + offline queue)."""
        if not self.received_at:
            return 0.0
        return (self.received_at - self.recorded_at).total_seconds()


class LocationAnomaly(models.Model):
    """A suspicious pattern observed while ingesting a fix.

    One anomaly never means fraud. Rate and repetition across days is what an
    administrator should look at, which is why every anomaly keeps its own row
    with structured ``details`` instead of a free-text flag on the update.
    """

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="location_anomalies"
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="location_anomalies",
    )
    location_update = models.ForeignKey(
        LocationUpdate, on_delete=models.CASCADE, related_name="anomalies"
    )
    anomaly_type = models.CharField(max_length=32, choices=AnomalyType.choices)
    severity = models.CharField(
        max_length=8, choices=AnomalySeverity.choices, default=AnomalySeverity.LOW
    )
    details = models.JSONField(
        default=dict, help_text="Structured evidence, e.g. computed speed and window."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "locations_locationanomaly"
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["user", "-created_at"], name="anomaly_user_created_idx"),
            models.Index(
                fields=["organization", "anomaly_type"], name="anomaly_org_type_idx"
            ),
            models.Index(fields=["severity"], name="anomaly_severity_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.anomaly_type} ({self.severity}) for user {self.user_id}"
