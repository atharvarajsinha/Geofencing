"""Infrastructure endpoints that are not part of the business API."""
from __future__ import annotations

from typing import Any

from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    """Liveness/readiness probe: verifies the database is reachable.

    There is no PostGIS to check: geofence maths runs in Python.
    """

    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = ()

    @extend_schema(exclude=True)
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        checks: dict[str, Any] = {"database": False, "database_version": None}
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version()")
                row = cursor.fetchone()
            checks["database"] = True
            checks["database_version"] = row[0] if row else None
        except Exception:  # noqa: BLE001 - probe must never leak a traceback
            return Response(
                {"success": False, "errors": {"detail": ["Database unavailable."]}},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"status": "ok", **checks})
