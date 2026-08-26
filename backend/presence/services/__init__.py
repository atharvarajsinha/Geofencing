"""Presence services.

* :mod:`presence.services.state_machine` - pure transition rules,
* :mod:`presence.services.processing`    - ingest orchestration (writes),
* :mod:`presence.services.staleness`     - timeout driven transitions.
"""
from presence.services.processing import (  # noqa: F401
    LocationIngestResult,
    PresenceOutcome,
    process_location_update,
)
from presence.services.staleness import (  # noqa: F401
    SweepResult,
    close_abandoned_presence_days,
    detect_stale_presences,
)
from presence.services.state_machine import (  # noqa: F401
    PresenceState,
    ReadingContext,
    TransitionDecision,
    apply_day_rollover,
    apply_reading,
    apply_timeout,
)

__all__ = [
    "LocationIngestResult",
    "PresenceOutcome",
    "PresenceState",
    "ReadingContext",
    "SweepResult",
    "TransitionDecision",
    "apply_day_rollover",
    "apply_reading",
    "apply_timeout",
    "close_abandoned_presence_days",
    "detect_stale_presences",
    "process_location_update",
]
