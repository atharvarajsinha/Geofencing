"""Presence URLs.

Mounted at ``/api/`` so that both the self-service (``/api/presence/...``) and
the administrative (``/api/admin/presence/...``) trees live in one app.
"""
from __future__ import annotations

from django.urls import path

from presence.views import (
    AdminPresenceEventListView,
    AdminPresenceListView,
    AdminPresenceSummaryView,
    AdminUserPresenceView,
    MyPresenceEventsView,
    MyPresenceHistoryView,
    MyPresenceView,
)

urlpatterns = [
    # --- Self service ----------------------------------------------------
    path("presence/me/", MyPresenceView.as_view(), name="presence-me"),
    path(
        "presence/me/history/",
        MyPresenceHistoryView.as_view(),
        name="presence-me-history",
    ),
    path("presence/me/events/", MyPresenceEventsView.as_view(), name="presence-me-events"),
    # --- Administration --------------------------------------------------
    path("admin/presence/", AdminPresenceListView.as_view(), name="admin-presence"),
    path(
        "admin/presence/summary/",
        AdminPresenceSummaryView.as_view(),
        name="admin-presence-summary",
    ),
    path(
        "admin/presence/events/",
        AdminPresenceEventListView.as_view(),
        name="admin-presence-events",
    ),
    path(
        "admin/presence/<int:user_id>/",
        AdminUserPresenceView.as_view(),
        name="admin-presence-user",
    ),
]
