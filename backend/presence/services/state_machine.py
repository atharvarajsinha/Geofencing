"""The presence state machine.

Pure functions only: no ORM, no clock, no configuration lookups. Everything the
decision depends on is passed in, which makes every branch testable in
microseconds and keeps the rules readable in one screen.

States and legal transitions
----------------------------

::

    UNKNOWN ──confident outside──────────────► OUTSIDE
       │                                          │
       │ N consecutive INSIDE readings            │ N consecutive INSIDE readings
       ▼                                          ▼
    PRESENT ◄──────────────────────────────── PRESENT
       │  ▲                                       ▲
       │  │ trusted reading (LOCATION_RESTORED)   │ M consecutive INSIDE readings
       │  │                                       │
       │  └──── STALE ◄── no update for T seconds │
       │                                          │
       └── M consecutive OUTSIDE readings ──► GONE ┘

Design decisions worth defending
--------------------------------

1. **Asymmetric thresholds.** Entering requires fewer confirmations than
   leaving (2 vs 3 by default). A false "present" is a minor annoyance; a false
   "left" wrongly ends somebody's attendance. Both numbers are configurable
   globally and per geofence.

2. **UNCERTAIN readings are inert.** They neither advance nor reset a streak.
   A device sitting in the hysteresis band therefore holds its state instead of
   oscillating, which is the whole point of the band.

3. **Streaks expire.** Two INSIDE readings three hours apart are not evidence
   of continuous presence, so a gap larger than ``streak_max_gap_seconds``
   resets both counters.

4. **Out-of-order deliveries are ignored for state.** A PWA flushing an offline
   queue can deliver an older fix after a newer one; applying it would rewind
   the machine. It is still stored as history.

5. **STALE is only reachable from PRESENT and only from the timeout task.** No
   reading can produce STALE, and silence can never produce GONE.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from geofences.enums import ContainmentVerdict
from presence.enums import PresenceEventType, PresenceStatus, TransitionReason


@dataclass(frozen=True)
class PresenceState:
    """Everything the machine needs to know about the current row."""

    status: str = PresenceStatus.UNKNOWN
    consecutive_inside: int = 0
    consecutive_outside: int = 0
    last_reading_at: datetime | None = None
    has_checked_in: bool = False


@dataclass(frozen=True)
class ReadingContext:
    """One evaluated GPS observation plus the applicable thresholds."""

    verdict: str
    recorded_at: datetime
    required_inside_readings: int
    required_outside_readings: int
    streak_max_gap_seconds: int


@dataclass(frozen=True)
class TransitionDecision:
    """What the caller must persist. ``events`` is ordered."""

    status: str
    consecutive_inside: int
    consecutive_outside: int
    events: tuple[tuple[str, str], ...] = ()  # (event_type, reason)
    status_changed: bool = False
    set_check_in: bool = False
    set_check_out: bool = False
    applied: bool = True
    skip_reason: str = ""
    streak_reset: bool = field(default=False)

    @property
    def emits_events(self) -> bool:
        return bool(self.events)


def _unchanged(state: PresenceState, *, skip_reason: str) -> TransitionDecision:
    return TransitionDecision(
        status=state.status,
        consecutive_inside=state.consecutive_inside,
        consecutive_outside=state.consecutive_outside,
        applied=False,
        skip_reason=skip_reason,
    )


def apply_reading(state: PresenceState, context: ReadingContext) -> TransitionDecision:
    """Advance the machine by one evaluated reading."""
    if (
        state.last_reading_at is not None
        and context.recorded_at <= state.last_reading_at
    ):
        # Older than what we already applied: keep it as history only.
        return _unchanged(state, skip_reason="OUT_OF_ORDER")

    inside = state.consecutive_inside
    outside = state.consecutive_outside
    streak_reset = False

    if state.last_reading_at is not None:
        gap = (context.recorded_at - state.last_reading_at).total_seconds()
        if gap > context.streak_max_gap_seconds:
            inside = outside = 0
            streak_reset = True

    if context.verdict == ContainmentVerdict.INSIDE:
        inside += 1
        outside = 0
    elif context.verdict == ContainmentVerdict.OUTSIDE:
        outside += 1
        inside = 0
    # UNCERTAIN: counters are left exactly as they are.

    status = state.status
    events: list[tuple[str, str]] = []
    set_check_in = False
    set_check_out = False

    # A trusted reading always ends a stale period: we can hear the device
    # again. STALE is only ever entered from PRESENT, so that is where we
    # return to before applying the normal rules below.
    if status == PresenceStatus.STALE:
        status = PresenceStatus.PRESENT
        events.append(
            (PresenceEventType.LOCATION_RESTORED, TransitionReason.UPDATES_RESUMED)
        )

    if status != PresenceStatus.PRESENT and inside >= context.required_inside_readings:
        status = PresenceStatus.PRESENT
        events.append((PresenceEventType.ENTERED, TransitionReason.CONSECUTIVE_INSIDE))
        set_check_in = not state.has_checked_in
    elif status == PresenceStatus.PRESENT and outside >= context.required_outside_readings:
        status = PresenceStatus.GONE
        events.append((PresenceEventType.EXITED, TransitionReason.CONSECUTIVE_OUTSIDE))
        set_check_out = True
    elif status == PresenceStatus.UNKNOWN and context.verdict == ContainmentVerdict.OUTSIDE:
        # Nothing happened yet and we now know where the device is: record it
        # without inventing an event, since the user never entered.
        status = PresenceStatus.OUTSIDE

    return TransitionDecision(
        status=status,
        # Clamp so the counters stay meaningful ("how close to the threshold")
        # instead of growing without bound while the user stays put.
        consecutive_inside=min(inside, context.required_inside_readings),
        consecutive_outside=min(outside, context.required_outside_readings),
        events=tuple(events),
        status_changed=status != state.status,
        set_check_in=set_check_in,
        set_check_out=set_check_out,
        applied=True,
        streak_reset=streak_reset,
    )


def apply_timeout(state: PresenceState) -> TransitionDecision:
    """Mark a silent PRESENT row as STALE.

    Silence is not departure: the user keeps ``check_in_at`` and no EXITED
    event is written. Only ``PRESENT`` rows are affected - a user who was
    already OUTSIDE, GONE or UNKNOWN has nothing to lose by staying quiet.
    """
    if state.status != PresenceStatus.PRESENT:
        return _unchanged(state, skip_reason="NOT_PRESENT")

    return TransitionDecision(
        status=PresenceStatus.STALE,
        # Reset the streaks: whatever the device was doing before the silence is
        # no longer evidence about where it is now.
        consecutive_inside=0,
        consecutive_outside=0,
        events=((PresenceEventType.STALE, TransitionReason.UPDATES_TIMED_OUT),),
        status_changed=True,
        applied=True,
    )


def apply_day_rollover(state: PresenceState) -> TransitionDecision:
    """Close an attendance day that ended while the user was still checked in.

    The day boundary is a bookkeeping event, not a movement, so the EXITED
    event it produces is explicitly marked with ``DAY_ROLLOVER``.
    """
    if state.status != PresenceStatus.PRESENT:
        return _unchanged(state, skip_reason="NOT_PRESENT")

    return TransitionDecision(
        status=PresenceStatus.GONE,
        consecutive_inside=0,
        consecutive_outside=0,
        events=((PresenceEventType.EXITED, TransitionReason.DAY_ROLLOVER),),
        status_changed=True,
        set_check_out=True,
        applied=True,
    )
