"""Presence enumerations.

The vocabulary matters as much as the code: ``GONE`` means "we watched this
person leave", ``STALE`` means "we stopped hearing from this device". Conflating
the two is the classic bug in attendance systems built on browser geolocation,
because a locked phone looks exactly like an empty room.
"""
from __future__ import annotations

from django.db import models


class PresenceStatus(models.TextChoices):
    UNKNOWN = "UNKNOWN", "No usable information yet"
    OUTSIDE = "OUTSIDE", "Confidently outside the area"
    PRESENT = "PRESENT", "Confidently inside the area"
    GONE = "GONE", "Was present and then confidently left"
    STALE = "STALE", "Was present, then updates stopped arriving"

    @classmethod
    def open_statuses(cls) -> tuple[str, ...]:
        """States that a running day can still transition out of."""
        return (cls.PRESENT.value, cls.STALE.value)


class PresenceEventType(models.TextChoices):
    ENTERED = "ENTERED", "Checked in"
    EXITED = "EXITED", "Checked out"
    STALE = "STALE", "Updates stopped arriving"
    LOCATION_RESTORED = "LOCATION_RESTORED", "Updates resumed after a gap"


class TransitionReason(models.TextChoices):
    """Why a transition happened - stored on the event for the audit trail."""

    CONSECUTIVE_INSIDE = "CONSECUTIVE_INSIDE", "Required inside readings reached"
    CONSECUTIVE_OUTSIDE = "CONSECUTIVE_OUTSIDE", "Required outside readings reached"
    UPDATES_TIMED_OUT = "UPDATES_TIMED_OUT", "No update within the stale timeout"
    UPDATES_RESUMED = "UPDATES_RESUMED", "A trusted update arrived after a timeout"
    DAY_ROLLOVER = "DAY_ROLLOVER", "Attendance day ended while still checked in"
