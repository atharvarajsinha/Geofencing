from __future__ import annotations

from rest_framework.routers import DefaultRouter

from organizations.views import OrganizationViewSet

router = DefaultRouter()
router.register("", OrganizationViewSet, basename="organization")

urlpatterns = router.urls
