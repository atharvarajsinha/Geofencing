"""State machine unit tests.

No database, no clock, no settings: the rules are pure functions, so these run
in milliseconds and pin down every branch of the transition table.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from geofences.enums import ContainmentVerdict
from presence.enums import PresenceEventType, PresenceStatus, TransitionReason
from presence.services.state_machine import (
    PresenceState,
    ReadingContext,
    apply_day_rollover,
    apply_reading,
    apply_timeout,
)

T0 = datetime(2026, 8, 26, 9, 0, tzinfo=timezone.utc)


def context(
    verdict: str,
    *,
    at: datetime = T0,
    required_inside: int = 2,
    required_outside: int = 3,
    gap: int = 300,
) -> ReadingContext:
    return ReadingContext(
        verdict=verdict,
        recorded_at=at,
        required_inside_readings=required_inside,
        required_outside_readings=required_outside,
        streak_max_gap_seconds=gap,
    )


def drive(state: PresenceState, verdicts: list[str], *, spacing: int = 60):
    """Feed a sequence of verdicts and return (state, all emitted events).

    Continues from the state's last reading so successive calls form one
    ordered stream; restarting the clock would make every follow-up reading
    look out of order.
    """
    events: list[str] = []
    at = T0 if state.last_reading_at is None else state.last_reading_at + timedelta(seconds=spacing)
    for verdict in verdicts:
        decision = apply_reading(state, context(verdict, at=at))
        events.extend(event for event, _ in decision.events)
        state = PresenceState(
            status=decision.status,
            consecutive_inside=decision.consecutive_inside,
            consecutive_outside=decision.consecutive_outside,
            last_reading_at=at,
            has_checked_in=state.has_checked_in or decision.set_check_in,
        )
        at = at + timedelta(seconds=spacing)
    return state, events


class TestEntry:
    def test_single_inside_reading_does_not_check_in(self):
        state, events = drive(PresenceState(), [ContainmentVerdict.INSIDE])
        assert state.status == PresenceStatus.UNKNOWN
        assert state.consecutive_inside == 1
        assert events == []

    def test_two_inside_readings_check_in(self):
        state, events = drive(
            PresenceState(), [ContainmentVerdict.INSIDE, ContainmentVerdict.INSIDE]
        )
        assert state.status == PresenceStatus.PRESENT
        assert events == [PresenceEventType.ENTERED]

    def test_entering_is_not_repeated_while_present(self):
        state, events = drive(PresenceState(), [ContainmentVerdict.INSIDE] * 6)
        assert state.status == PresenceStatus.PRESENT
        assert events.count(PresenceEventType.ENTERED) == 1

    def test_required_readings_are_configurable(self):
        decision = apply_reading(
            PresenceState(consecutive_inside=0, last_reading_at=None),
            context(ContainmentVerdict.INSIDE, required_inside=1),
        )
        assert decision.status == PresenceStatus.PRESENT


class TestExit:
    def test_one_outside_reading_does_not_check_out(self):
        state, _ = drive(PresenceState(), [ContainmentVerdict.INSIDE] * 2)
        state, events = drive(state, [ContainmentVerdict.OUTSIDE])
        assert state.status == PresenceStatus.PRESENT
        assert events == []

    def test_three_outside_readings_check_out(self):
        state, _ = drive(PresenceState(), [ContainmentVerdict.INSIDE] * 2)
        state, events = drive(state, [ContainmentVerdict.OUTSIDE] * 3)
        assert state.status == PresenceStatus.GONE
        assert events == [PresenceEventType.EXITED]

    def test_check_in_is_kept_when_re_entering(self):
        state, _ = drive(
            PresenceState(),
            [ContainmentVerdict.INSIDE] * 2 + [ContainmentVerdict.OUTSIDE] * 3,
        )
        assert state.status == PresenceStatus.GONE
        decision = apply_reading(state, context(ContainmentVerdict.INSIDE, at=T0 + timedelta(seconds=600)))
        # The streak expired during the gap, so one reading is not enough...
        assert decision.status == PresenceStatus.GONE
        state = PresenceState(
            status=decision.status,
            consecutive_inside=decision.consecutive_inside,
            consecutive_outside=decision.consecutive_outside,
            last_reading_at=T0 + timedelta(seconds=600),
            has_checked_in=True,
        )
        decision = apply_reading(state, context(ContainmentVerdict.INSIDE, at=T0 + timedelta(seconds=660)))
        assert decision.status == PresenceStatus.PRESENT
        # ...and re-entry must not overwrite the original check-in time.
        assert decision.set_check_in is False


class TestJitter:
    def test_uncertain_readings_never_change_state(self):
        state, _ = drive(PresenceState(), [ContainmentVerdict.INSIDE] * 2)
        state, events = drive(state, [ContainmentVerdict.UNCERTAIN] * 10)
        assert state.status == PresenceStatus.PRESENT
        assert events == []

    def test_uncertain_readings_do_not_reset_a_streak(self):
        state, events = drive(
            PresenceState(),
            [
                ContainmentVerdict.INSIDE,
                ContainmentVerdict.UNCERTAIN,
                ContainmentVerdict.INSIDE,
            ],
        )
        assert state.status == PresenceStatus.PRESENT
        assert events == [PresenceEventType.ENTERED]

    def test_a_single_outside_blip_does_not_end_presence(self):
        state, _ = drive(PresenceState(), [ContainmentVerdict.INSIDE] * 2)
        state, events = drive(
            state,
            [
                ContainmentVerdict.OUTSIDE,
                ContainmentVerdict.OUTSIDE,
                ContainmentVerdict.INSIDE,  # resets the outside streak
                ContainmentVerdict.OUTSIDE,
                ContainmentVerdict.OUTSIDE,
            ],
        )
        assert state.status == PresenceStatus.PRESENT
        assert events == []

    def test_streak_expires_after_a_long_gap(self):
        state = PresenceState(
            status=PresenceStatus.UNKNOWN,
            consecutive_inside=1,
            last_reading_at=T0,
        )
        decision = apply_reading(
            state,
            context(ContainmentVerdict.INSIDE, at=T0 + timedelta(seconds=3600), gap=300),
        )
        assert decision.streak_reset is True
        assert decision.status == PresenceStatus.UNKNOWN
        assert decision.consecutive_inside == 1


class TestOrdering:
    def test_out_of_order_reading_is_ignored(self):
        state = PresenceState(status=PresenceStatus.PRESENT, last_reading_at=T0)
        decision = apply_reading(
            state, context(ContainmentVerdict.OUTSIDE, at=T0 - timedelta(seconds=120))
        )
        assert decision.applied is False
        assert decision.skip_reason == "OUT_OF_ORDER"
        assert decision.status == PresenceStatus.PRESENT


class TestStale:
    def test_timeout_marks_present_as_stale_not_gone(self):
        decision = apply_timeout(PresenceState(status=PresenceStatus.PRESENT))
        assert decision.status == PresenceStatus.STALE
        assert decision.events == (
            (PresenceEventType.STALE, TransitionReason.UPDATES_TIMED_OUT),
        )
        assert decision.set_check_out is False

    @pytest.mark.parametrize(
        "status",
        [
            PresenceStatus.UNKNOWN,
            PresenceStatus.OUTSIDE,
            PresenceStatus.GONE,
            PresenceStatus.STALE,
        ],
    )
    def test_timeout_only_applies_to_present(self, status):
        decision = apply_timeout(PresenceState(status=status))
        assert decision.applied is False
        assert decision.status == status

    def test_resuming_updates_restores_presence(self):
        state = PresenceState(status=PresenceStatus.STALE, has_checked_in=True)
        decision = apply_reading(state, context(ContainmentVerdict.INSIDE))
        assert decision.status == PresenceStatus.PRESENT
        assert decision.events[0][0] == PresenceEventType.LOCATION_RESTORED

    def test_resuming_outside_can_still_lead_to_exit(self):
        state = PresenceState(status=PresenceStatus.STALE, has_checked_in=True)
        state, events = drive(state, [ContainmentVerdict.OUTSIDE] * 3)
        assert events[0] == PresenceEventType.LOCATION_RESTORED
        assert events[-1] == PresenceEventType.EXITED
        assert state.status == PresenceStatus.GONE


class TestUnknownAndRollover:
    def test_unknown_becomes_outside_without_an_event(self):
        decision = apply_reading(PresenceState(), context(ContainmentVerdict.OUTSIDE))
        assert decision.status == PresenceStatus.OUTSIDE
        assert decision.events == ()

    def test_day_rollover_closes_an_open_day(self):
        decision = apply_day_rollover(PresenceState(status=PresenceStatus.PRESENT))
        assert decision.status == PresenceStatus.GONE
        assert decision.set_check_out is True
        assert decision.events == (
            (PresenceEventType.EXITED, TransitionReason.DAY_ROLLOVER),
        )
