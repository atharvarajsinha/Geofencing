"""Time helpers.

The distinction between *when the fix was taken* (``recorded_at``) and *when the
server saw it* (``received_at``) matters everywhere in this project, so the
helpers that convert between them live in one place.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone


def utc_now() -> datetime:
    """Timezone-aware current time in UTC."""
    return timezone.now()


def seconds_between(earlier: datetime, later: datetime) -> float:
    """Signed number of seconds from ``earlier`` to ``later``."""
    return (later - earlier).total_seconds()


def age_seconds(moment: datetime, *, now: datetime | None = None) -> float:
    """How old ``moment`` is, in seconds (negative when in the future)."""
    return seconds_between(moment, now or utc_now())


def resolve_timezone(name: str | None) -> ZoneInfo:
    """Return a ``ZoneInfo`` for ``name``, falling back to UTC."""
    if not name:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def local_date(moment: datetime, tz_name: str | None) -> date:
    """Calendar date of ``moment`` in the organization's timezone.

    Attendance is a human, local-calendar concept: a shift that starts at
    08:00 in Asia/Kolkata belongs to that local day even though the instant is
    stored in UTC.
    """
    if timezone.is_naive(moment):
        moment = moment.replace(tzinfo=dt_timezone.utc)
    return moment.astimezone(resolve_timezone(tz_name)).date()


def day_bounds_utc(day: date, tz_name: str | None) -> tuple[datetime, datetime]:
    """UTC ``[start, end)`` instants covering a local calendar day."""
    tz = resolve_timezone(tz_name)
    start_local = datetime.combine(day, datetime.min.time(), tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(dt_timezone.utc), end_local.astimezone(dt_timezone.utc)
