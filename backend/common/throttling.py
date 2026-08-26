"""Throttling classes.

The location ingest endpoint is the only one a PWA calls continuously, so it
gets its own bucket keyed by user (never by IP alone: an entire campus usually
shares one NAT address).

All classes here **fail open**. Rate limiting is a protection mechanism, not a
correctness one, and a cache outage must not take the whole API down with it -
which is exactly what happens with the stock DRF classes, because they call the
cache before the view runs. The trade-off is explicit: during a Redis outage
requests are unthrottled, and every occurrence is logged.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.core.exceptions import ImproperlyConfigured
from rest_framework.request import Request
from rest_framework.settings import api_settings
from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle

if TYPE_CHECKING:  # pragma: no cover
    # Imported lazily: these classes are DRF's DEFAULT_THROTTLE_CLASSES, and
    # rest_framework.views resolves that setting while its own module is still
    # executing. A module level import here would be circular.
    from rest_framework.views import APIView

logger = logging.getLogger("geofencing.throttling")


class FailOpenThrottleMixin:
    """Allow the request when the throttle backend is unreachable.

    Also resolves the configured rate per request instead of trusting
    ``SimpleRateThrottle.THROTTLE_RATES``, which DRF binds to the settings dict
    once, at class definition time. That snapshot never sees a later change, so
    a runtime reconfiguration - or an ``override_settings`` block in a test -
    was silently ignored and the endpoint ran at its import-time rate.
    """

    def get_rate(self) -> str | None:
        scope = getattr(self, "scope", None)
        if not scope:
            return None
        try:
            return api_settings.DEFAULT_THROTTLE_RATES[scope]
        except KeyError:
            # Loud, like DRF: an endpoint declaring a scope with no configured
            # rate is a deployment mistake, not a request to run unthrottled.
            raise ImproperlyConfigured(
                f"No throttle rate is configured for the scope {scope!r}."
            ) from None

    def allow_request(self, request: Request, view: "APIView") -> bool:
        try:
            return super().allow_request(request, view)  # type: ignore[misc]
        except Exception:  # noqa: BLE001 - any cache failure must not 500
            logger.warning(
                "Throttle backend unavailable; allowing request to %s unthrottled.",
                getattr(request, "path", "?"),
                exc_info=True,
            )
            return True


class UserScopedRateThrottle(FailOpenThrottleMixin, ScopedRateThrottle):
    """Scoped throttle keyed by authenticated user, falling back to IP."""

    def get_cache_key(self, request: Request, view: "APIView") -> str | None:
        if not getattr(self, "scope", None):
            return None
        if request.user and request.user.is_authenticated:
            ident = str(request.user.pk)
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class AnonymousLoginThrottle(FailOpenThrottleMixin, SimpleRateThrottle):
    """Protect the credential endpoint from password spraying.

    Keyed by IP *and* submitted email so that one attacker cannot lock out a
    legitimate user by exhausting their bucket from a different address.
    """

    scope = "auth"

    def get_cache_key(self, request: Request, view: "APIView") -> str | None:
        identifier = ""
        if isinstance(getattr(request, "data", None), dict):
            identifier = str(request.data.get("email", ""))[:150].lower()
        return self.cache_format % {
            "scope": self.scope,
            "ident": f"{self.get_ident(request)}:{identifier}",
        }
