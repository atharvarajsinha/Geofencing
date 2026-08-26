from __future__ import annotations

from django.urls import path

from locations.views import (
    AnomalyListView,
    LocationStatusView,
    LocationUpdateView,
    MyLocationHistoryView,
)

urlpatterns = [
    path("update/", LocationUpdateView.as_view(), name="location-update"),
    path("status/", LocationStatusView.as_view(), name="location-status"),
    path("history/", MyLocationHistoryView.as_view(), name="location-history"),
    # Admin only: advisory anomaly feed used by the fraud review screen.
    path("anomalies/", AnomalyListView.as_view(), name="location-anomalies"),
]
