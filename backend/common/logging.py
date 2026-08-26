"""Request-scoped logging helpers."""
from __future__ import annotations

import contextvars
import logging

#: Correlation id for the request currently being handled by this thread.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class RequestIDFilter(logging.Filter):
    """Inject ``request_id`` into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True
