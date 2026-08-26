"""Read-side queries for geofences."""
from __future__ import annotations

from django.db.models import QuerySet

from common.exceptions import NotFound
from geofences.models import Geofence


def geofences_for_organization(
    organization_id: int, *, only_active: bool = False
) -> QuerySet[Geofence]:
    queryset = Geofence.objects.for_organization(organization_id).select_related(
        "organization"
    )
    return queryset.active() if only_active else queryset


def visible_geofences_for(user) -> QuerySet[Geofence]:
    """Geofences the caller may read."""
    if user.is_platform_admin:
        return Geofence.objects.select_related("organization")
    if not user.organization_id:
        return Geofence.objects.none()
    return geofences_for_organization(user.organization_id)


def get_geofence_for_organization(*, geofence_id: int, organization_id: int) -> Geofence:
    geofence = (
        Geofence.objects.for_organization(organization_id).filter(pk=geofence_id).first()
    )
    if geofence is None:
        # Deliberately the same response as a non-existent id: never confirm
        # the existence of another organization's geofence.
        raise NotFound("Geofence not found.")
    return geofence


def active_geofence_ids(organization_id: int) -> list[int]:
    return list(
        Geofence.objects.for_organization(organization_id)
        .active()
        .values_list("id", flat=True)
    )
