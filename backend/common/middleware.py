"""Project middleware."""
from __future__ import annotations

import uuid
from typing import Callable

from django.http import HttpRequest, HttpResponse

from common.logging import request_id_var

REQUEST_ID_HEADER = "HTTP_X_REQUEST_ID"
RESPONSE_HEADER = "X-Request-ID"


class RequestIDMiddleware:
    """Attach a correlation id to every request/response and to log records.

    A PWA that retries a failed location update can reuse the same
    ``X-Request-ID`` header, which makes duplicate delivery trivially greppable
    in the logs. Idempotency itself is handled by ``client_event_id`` in the
    payload, not by this header.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.META.get(REQUEST_ID_HEADER, "")
        request_id = incoming[:64] if incoming else uuid.uuid4().hex
        request.request_id = request_id  # type: ignore[attr-defined]
        token = request_id_var.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token)
        response[RESPONSE_HEADER] = request_id
        return response
