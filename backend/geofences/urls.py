from __future__ import annotations

from rest_framework.routers import DefaultRouter

from geofences.views import GeofenceViewSet

router = DefaultRouter()
router.register("", GeofenceViewSet, basename="geofence")

urlpatterns = router.urls
