"""Location enumerations."""
from __future__ import annotations

from django.db import models


class AnomalyType(models.TextChoices):
    """Signals that a reading may not describe reality.

    None of these prove spoofing on their own - browser geolocation cannot be
    trusted the way a hardware-attested mobile SDK can. They exist to surface
    patterns for a human to review.
    """

    IMPOSSIBLE_SPEED = "IMPOSSIBLE_SPEED", "Implied speed exceeds the plausible maximum"
    COORDINATE_JUMP = "COORDINATE_JUMP", "Large positional jump in a short window"
    FUTURE_TIMESTAMP = "FUTURE_TIMESTAMP", "recorded_at is in the future"
    STATIONARY_REPEAT = "STATIONARY_REPEAT", "Identical coordinates repeated for a long period"
    POOR_ACCURACY = "POOR_ACCURACY", "Accuracy worse than the acceptable threshold"
    HIGH_FREQUENCY = "HIGH_FREQUENCY", "Update rate above the expected maximum"
    STALE_READING = "STALE_READING", "Fix is old but still within the accepted window"


class AnomalySeverity(models.TextChoices):
    LOW = "LOW", "Informational"
    MEDIUM = "MEDIUM", "Worth reviewing"
    HIGH = "HIGH", "Reading excluded from presence decisions"

    @classmethod
    def order(cls) -> dict[str, int]:
        return {cls.LOW.value: 0, cls.MEDIUM.value: 1, cls.HIGH.value: 2}
