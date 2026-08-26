"""Presence filters (django-filter)."""
from __future__ import annotations

from django_filters import rest_framework as filters

from presence.enums import PresenceEventType, PresenceStatus
from presence.models import Presence, PresenceEvent


class PresenceFilterSet(filters.FilterSet):
    user = filters.NumberFilter(field_name="user_id")
    geofence = filters.NumberFilter(field_name="geofence_id")
    status = filters.MultipleChoiceFilter(
        field_name="status", choices=PresenceStatus.choices
    )
    date = filters.DateFilter(field_name="date")
    date_from = filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to = filters.DateFilter(field_name="date", lookup_expr="lte")
    last_seen_before = filters.IsoDateTimeFilter(
        field_name="last_seen_at", lookup_expr="lt"
    )
    last_seen_after = filters.IsoDateTimeFilter(
        field_name="last_seen_at", lookup_expr="gte"
    )
    search = filters.CharFilter(method="filter_search", label="User name or email")

    class Meta:
        model = Presence
        fields = ("user", "geofence", "status", "date")

    def filter_search(self, queryset, name: str, value: str):
        return queryset.filter(user__name__icontains=value) | queryset.filter(
            user__email__icontains=value
        )


class PresenceEventFilterSet(filters.FilterSet):
    user = filters.NumberFilter(field_name="user_id")
    geofence = filters.NumberFilter(field_name="geofence_id")
    event_type = filters.MultipleChoiceFilter(
        field_name="event_type", choices=PresenceEventType.choices
    )
    date = filters.DateFilter(field_name="timestamp", lookup_expr="date")
    timestamp_after = filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr="gte")
    timestamp_before = filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr="lte")

    class Meta:
        model = PresenceEvent
        fields = ("user", "geofence", "event_type")
