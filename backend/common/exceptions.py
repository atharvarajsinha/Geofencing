"""Domain exceptions and the project-wide DRF exception handler.

Services raise plain domain exceptions; the handler is the only place that
knows about HTTP status codes, so business code never imports ``rest_framework``
just to signal a conflict.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("geofencing.api")


class ApplicationError(Exception):
    """Base class for expected, recoverable business errors.

    ``errors`` mirrors the DRF validation error shape so that clients can
    handle field errors uniformly regardless of where they originated.
    """

    status_code: int = status.HTTP_400_BAD_REQUEST
    default_message: str = "Request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        errors: dict[str, Any] | None = None,
        code: str | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.errors = errors or {"detail": [self.message]}
        self.code = code
        super().__init__(self.message)


class ValidationFailed(ApplicationError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_message = "Validation failed."


class NotFound(ApplicationError):
    status_code = status.HTTP_404_NOT_FOUND
    default_message = "Resource not found."


class PermissionDenied(ApplicationError):
    status_code = status.HTTP_403_FORBIDDEN
    default_message = "You do not have permission to perform this action."


class Conflict(ApplicationError):
    """Concurrent or contradictory state change."""

    status_code = status.HTTP_409_CONFLICT
    default_message = "The request conflicts with the current state."


def _normalise_detail(detail: Any) -> dict[str, Any]:
    """Coerce any DRF error detail into ``{field: [messages]}``."""
    if isinstance(detail, dict):
        return {
            key: value if isinstance(value, (list, dict)) else [value]
            for key, value in detail.items()
        }
    if isinstance(detail, list):
        return {"detail": detail}
    return {"detail": [detail]}


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Return the project error envelope for every failure mode.

    Unhandled exceptions are logged with a correlation id and reported as an
    opaque 500; raw Python exception text is never exposed to clients.
    """
    if isinstance(exc, DjangoValidationError):
        exc = drf_exceptions.ValidationError(detail=exc.message_dict
                                             if hasattr(exc, "message_dict")
                                             else list(exc.messages))
    elif isinstance(exc, DjangoPermissionDenied):
        exc = drf_exceptions.PermissionDenied()
    elif isinstance(exc, Http404):
        exc = drf_exceptions.NotFound()

    if isinstance(exc, ApplicationError):
        return Response(
            {"success": False, "errors": exc.errors},
            status=exc.status_code,
        )

    if isinstance(exc, IntegrityError):
        logger.warning("Integrity error surfaced to the API layer: %s", exc)
        return Response(
            {
                "success": False,
                "errors": {"detail": ["The request conflicts with existing data."]},
            },
            status=status.HTTP_409_CONFLICT,
        )

    response = drf_exception_handler(exc, context)

    if response is None:
        error_id = uuid.uuid4().hex
        request = context.get("request")
        logger.exception(
            "Unhandled exception %s on %s",
            error_id,
            getattr(request, "path", "?"),
        )
        return Response(
            {
                "success": False,
                "errors": {
                    "detail": ["Internal server error."],
                    "error_id": [error_id],
                },
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    response.data = {"success": False, "errors": _normalise_detail(response.data)}
    return response
