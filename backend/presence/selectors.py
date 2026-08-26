"""Read-side queries for presence and its history."""
from __future__ import annotations

from datetime import date as date_type
from datetime import datetime

from django.db.models import Count, Q, QuerySet

from accounts.models import User
from common.utils.time import local_date, utc_now
from presence.enums import PresenceStatus
from presence.models import Presence, PresenceEvent

#: Which state wins when a user has rows in several geofences at once.
#: "Present somewhere" beats "unknown everywhere".
STATUS_PRIORITY: dict[str, int] = {
    PresenceStatus.PRESENT: 5,
    PresenceStatus.STALE: 4,
    PresenceStatus.GONE: 3,
    PresenceStatus.OUTSIDE: 2,
    PresenceStatus.UNKNOWN: 1,
}


def attendance_date_for(user: User, moment: datetime | None = None) -> date_type:
    """Today's attendance date in the user's organization timezone."""
    timezone_name = user.organization.timezone if user.organization_id else "UTC"
    return local_date(moment or utc_now(), timezone_name)


def presence_rows_for_user(
    user_id: int, *, day: date_type | None = None
) -> QuerySet[Presence]:
    queryset = (
        Presence.objects.for_user(user_id)
        .with_related()
        .order_by("-date", "geofence_id")
    )
    if day is not None:
        queryset = queryset.on_date(day)
    return queryset


def effective_presence(rows: list[Presence]) -> Presence | None:
    """The row that best describes where the user is right now."""
    if not rows:
        return None
    return max(
        rows,
        key=lambda row: (
            STATUS_PRIORITY.get(row.status, 0),
            row.last_seen_at or row.updated_at,
        ),
    )


def effective_status(rows: list[Presence]) -> str:
    row = effective_presence(rows)
    return row.status if row is not None else PresenceStatus.UNKNOWN


def organization_presence(organization_id: int) -> QuerySet[Presence]:
    return Presence.objects.for_organization(organization_id).with_related()


def presence_events(organization_id: int) -> QuerySet[PresenceEvent]:
    return (
        PresenceEvent.objects.for_organization(organization_id)
        .with_related()
        .order_by("-timestamp", "-id")
    )


def user_presence_events(user_id: int) -> QuerySet[PresenceEvent]:
    return (
        PresenceEvent.objects.filter(user_id=user_id)
        .select_related("geofence")
        .order_by("-timestamp", "-id")
    )


def presence_summary(
    *, organization_id: int, day: date_type, geofence_id: int | None = None
) -> dict[str, int]:
    """Dashboard counters for one attendance day.

    Counted per *user*, not per row: somebody PRESENT in one geofence and
    OUTSIDE another is one present user. Members without any row for the day
    are UNKNOWN - which is the honest answer, not "absent".
    """
    rows = Presence.objects.for_organization(organization_id).on_date(day)
    if geofence_id is not None:
        rows = rows.filter(geofence_id=geofence_id)

    best_status_by_user: dict[int, str] = {}
    for user_id, status in rows.values_list("user_id", "status"):
        current = best_status_by_user.get(user_id)
        if current is None or STATUS_PRIORITY.get(status, 0) > STATUS_PRIORITY.get(
            current, 0
        ):
            best_status_by_user[user_id] = status

    counts = {status.value: 0 for status in PresenceStatus}
    for status in best_status_by_user.values():
        counts[status] = counts.get(status, 0) + 1

    total_users = User.objects.filter(
        organization_id=organization_id, is_active=True
    ).count()
    # Everybody the system has heard nothing usable from today.
    counts[PresenceStatus.UNKNOWN] = max(
        total_users - sum(value for key, value in counts.items() if key != PresenceStatus.UNKNOWN),
        0,
    )

    return {
        "date": day.isoformat(),
        "total_users": total_users,
        "present": counts[PresenceStatus.PRESENT],
        "gone": counts[PresenceStatus.GONE],
        "outside": counts[PresenceStatus.OUTSIDE],
        "stale": counts[PresenceStatus.STALE],
        "unknown": counts[PresenceStatus.UNKNOWN],
        "tracked_users": len(best_status_by_user),
    }


def geofence_occupancy(
    *, organization_id: int, day: date_type
) -> list[dict[str, object]]:
    """Per-geofence headcount for the dashboard."""
    rows = (
        Presence.objects.for_organization(organization_id)
        .on_date(day)
        .values("geofence_id", "geofence__name")
        .annotate(
            present=Count("id", filter=Q(status=PresenceStatus.PRESENT)),
            stale=Count("id", filter=Q(status=PresenceStatus.STALE)),
            gone=Count("id", filter=Q(status=PresenceStatus.GONE)),
            outside=Count("id", filter=Q(status=PresenceStatus.OUTSIDE)),
        )
        .order_by("geofence__name")
    )
    return [
        {
            "geofence_id": row["geofence_id"],
            "geofence_name": row["geofence__name"],
            "present": row["present"],
            "stale": row["stale"],
            "gone": row["gone"],
            "outside": row["outside"],
        }
        for row in rows
    ]
