"""Root URL configuration.

The API surface is versionless by path but documented through OpenAPI; every
endpoint lives under ``/api/``.
"""
from __future__ import annotations

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from common.views import HealthCheckView

admin_url = getattr(settings, "ADMIN_URL", "admin/")

urlpatterns = [
    path(admin_url, admin.site.urls),
    path("health/", HealthCheckView.as_view(), name="health-check"),
    # --- API -------------------------------------------------------------
    path("api/auth/", include(("accounts.urls", "accounts"), namespace="auth")),
    path("api/geofences/", include(("geofences.urls", "geofences"), namespace="geofences")),
    path("api/location/", include(("locations.urls", "locations"), namespace="locations")),
    path("api/", include(("presence.urls", "presence"), namespace="presence")),
    path(
        "api/organizations/",
        include(("organizations.urls", "organizations"), namespace="organizations"),
    ),
    # --- Documentation ---------------------------------------------------
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
