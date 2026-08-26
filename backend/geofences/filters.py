"""Geofence filters."""
from __future__ import annotations

from django_filters import rest_framework as filters

from geofences.models import Geofence


class GeofenceFilterSet(filters.FilterSet):
    type = filters.CharFilter(field_name="geofence_type", lookup_expr="iexact")
    is_active = filters.BooleanFilter(field_name="is_active")
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    created_after = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Geofence
        fields = ("type", "is_active", "name")
