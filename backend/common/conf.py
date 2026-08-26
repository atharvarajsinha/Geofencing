"""Typed access to the ``settings.GEOFENCING`` tunables.

Reading tunables through this object instead of ``settings.GEOFENCING["..."]``
gives us three things:

* a single place that documents every knob,
* attribute access that fails loudly on a typo instead of a ``KeyError`` deep
  inside the state machine,
* an easy override point in tests (``override_settings(GEOFENCING={...})``)
  because the values are resolved lazily on every access.
"""
from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

#: Every supported key with the value used when the deployment omits it.
DEFAULTS: dict[str, Any] = {
    "MIN_RADIUS_M": 10.0,
    "MAX_RADIUS_M": 50_000.0,
    "MAX_GEOFENCE_AREA_KM2": 500.0,
    "DEFAULT_ENTRY_BUFFER_M": 0.0,
    "DEFAULT_EXIT_BUFFER_M": 40.0,
    "MAX_ACCEPTABLE_ACCURACY_M": 50.0,
    "HARD_REJECT_ACCURACY_M": 1000.0,
    "ACCURACY_MARGIN_FACTOR": 1.0,
    "ACCURACY_MARGIN_CAP_M": 150.0,
    "REQUIRED_INSIDE_READINGS": 2,
    "REQUIRED_OUTSIDE_READINGS": 3,
    "STREAK_MAX_GAP_SECONDS": 300,
    "STALE_AFTER_SECONDS": 300,
    "MAX_LOCATION_AGE_SECONDS": 3600,
    "MAX_CLOCK_SKEW_SECONDS": 120,
    "MAX_PLAUSIBLE_SPEED_KMH": 300.0,
    "JUMP_DISTANCE_M": 5_000.0,
    "JUMP_WINDOW_SECONDS": 60,
    "STATIONARY_TOLERANCE_M": 1.0,
    "STATIONARY_MIN_SECONDS": 1800,
    "STATIONARY_MIN_READINGS": 10,
    "MAX_UPDATES_PER_MINUTE": 30,
    "RECOMMENDED_PING_INTERVAL_SECONDS": 60,
    "LOCATION_HISTORY_RETENTION_DAYS": 30,
    "PRESENCE_EVENT_RETENTION_DAYS": 365,
    "ANOMALY_RETENTION_DAYS": 90,
    "MAX_GEOFENCES_EVALUATED_PER_UPDATE": 50,
}


class GeofencingConf:
    """Lazy, attribute-style reader for ``settings.GEOFENCING``."""

    __slots__ = ()

    def __getattr__(self, name: str) -> Any:
        if name not in DEFAULTS:
            raise AttributeError(
                f"Unknown geofencing setting {name!r}. "
                f"Add it to common.conf.DEFAULTS first."
            )
        return getattr(settings, "GEOFENCING", {}).get(name, DEFAULTS[name])

    def as_dict(self) -> dict[str, Any]:
        """Full resolved configuration (used by the client-facing config API)."""
        return {key: getattr(self, key) for key in DEFAULTS}

    def check(self) -> None:
        """Validate cross-field invariants at startup."""
        if self.REQUIRED_INSIDE_READINGS < 1 or self.REQUIRED_OUTSIDE_READINGS < 1:
            raise ImproperlyConfigured(
                "REQUIRED_INSIDE_READINGS/REQUIRED_OUTSIDE_READINGS must be >= 1."
            )
        if self.MAX_ACCEPTABLE_ACCURACY_M <= 0:
            raise ImproperlyConfigured("MAX_ACCEPTABLE_ACCURACY_M must be positive.")
        if self.HARD_REJECT_ACCURACY_M < self.MAX_ACCEPTABLE_ACCURACY_M:
            raise ImproperlyConfigured(
                "HARD_REJECT_ACCURACY_M must be >= MAX_ACCEPTABLE_ACCURACY_M."
            )
        if self.DEFAULT_EXIT_BUFFER_M <= self.DEFAULT_ENTRY_BUFFER_M:
            raise ImproperlyConfigured(
                "DEFAULT_EXIT_BUFFER_M must be greater than DEFAULT_ENTRY_BUFFER_M; "
                "an exit band that is not wider than the entry band provides no "
                "hysteresis at all."
            )
        if self.MAX_LOCATION_AGE_SECONDS < self.STALE_AFTER_SECONDS:
            raise ImproperlyConfigured(
                "MAX_LOCATION_AGE_SECONDS must be >= STALE_AFTER_SECONDS, otherwise a "
                "client recovering from an outage can never restore its presence."
            )


#: Singleton used across the project.
geo_conf = GeofencingConf()
