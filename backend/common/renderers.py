"""Response envelope.

Every successful API response is rendered as::

    {"success": true, "data": {...}}

and every error as::

    {"success": false, "errors": {...}}

Wrapping happens in the renderer rather than in each view so that no endpoint
can forget it, including the ones provided by third party packages
(SimpleJWT, drf-spectacular error responses, ...).
"""
from __future__ import annotations

from typing import Any

from rest_framework.renderers import JSONRenderer

ENVELOPE_KEYS = frozenset({"success", "data", "errors"})


def _already_enveloped(data: Any) -> bool:
    return isinstance(data, dict) and "success" in data and ENVELOPE_KEYS.issuperset(data)


class EnvelopeJSONRenderer(JSONRenderer):
    """Wrap payloads in the project-wide success/error envelope."""

    def render(
        self,
        data: Any,
        accepted_media_type: str | None = None,
        renderer_context: dict[str, Any] | None = None,
    ) -> bytes:
        renderer_context = renderer_context or {}
        response = renderer_context.get("response")

        if data is None:
            payload: Any = {"success": True, "data": None}
        elif _already_enveloped(data):
            payload = data
        elif response is not None and response.status_code >= 400:
            # Errors are normalised by common.exceptions.api_exception_handler;
            # anything reaching this branch was raised outside DRF's handler.
            payload = {"success": False, "errors": data}
        else:
            payload = {"success": True, "data": data}

        return super().render(payload, accepted_media_type, renderer_context)
