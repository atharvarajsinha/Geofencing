"""Presence serializers."""
from __future__ import annotations

from typing import Any

from rest_framework import serializers

from common.utils.time import utc_now
from presence.models import Presence, PresenceEvent


class PresenceSerializer(serializers.ModelSerializer):
    """A presence row as the dashboard needs it."""

    user_id = serializers.IntegerField(read_only=True)
    user_name = serializers.CharField(source="user.name", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    geofence_id = serializers.IntegerField(read_only=True)
    geofence_name = serializers.CharField(source="geofence.name", read_only=True)
    seconds_since_last_seen = serializers.SerializerMethodField()
    current_location = serializers.SerializerMethodField()

    class Meta:
        model = Presence
        fields = (
            "id",
            "user_id",
            "user_name",
            "user_email",
            "organization_id",
            "geofence_id",
            "geofence_name",
            "date",
            "status",
            "check_in_at",
            "check_out_at",
            "last_seen_at",
            "seconds_since_last_seen",
            "stale_since",
            "current_location",
            "last_verdict",
            "last_distance_m",
            "consecutive_inside",
            "consecutive_outside",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_seconds_since_last_seen(self, obj: Presence) -> float | None:
        if obj.last_seen_at is None:
            return None
        return round((utc_now() - obj.last_seen_at).total_seconds(), 1)

    def get_current_location(self, obj: Presence) -> dict[str, Any] | None:
        """Last known position, with its accuracy.

        Exposed as one object so that a client can never plot a coordinate
        without the accuracy that qualifies it.
        """
        if obj.last_latitude is None or obj.last_longitude is None:
            return None
        return {
            "latitude": obj.last_latitude,
            "longitude": obj.last_longitude,
            "accuracy": obj.last_accuracy,
            "recorded_at": obj.last_seen_at,
        }


class PresenceEventSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    geofence_name = serializers.CharField(source="geofence.name", read_only=True)

    class Meta:
        model = PresenceEvent
        fields = (
            "id",
            "user",
            "user_name",
            "user_email",
            "organization",
            "geofence",
            "geofence_name",
            "presence",
            "event_type",
            "reason",
            "previous_status",
            "new_status",
            "latitude",
            "longitude",
            "accuracy",
            "timestamp",
            "metadata",
            "created_at",
        )
        read_only_fields = fields


class MyPresenceSerializer(serializers.Serializer):
    """Composite payload for ``GET /api/presence/me/``."""

    date = serializers.DateField()
    effective_status = serializers.CharField()
    geofences = PresenceSerializer(many=True)


class PresenceSummarySerializer(serializers.Serializer):
    """Documentation schema for the dashboard counters."""

    date = serializers.CharField()
    total_users = serializers.IntegerField()
    tracked_users = serializers.IntegerField()
    present = serializers.IntegerField()
    gone = serializers.IntegerField()
    outside = serializers.IntegerField()
    stale = serializers.IntegerField()
    unknown = serializers.IntegerField()
    by_geofence = serializers.ListField(child=serializers.DictField())


class AdminUserPresenceSerializer(serializers.Serializer):
    """Documentation schema for ``GET /api/admin/presence/{user_id}/``."""

    user_id = serializers.IntegerField()
    date = serializers.DateField()
    effective_status = serializers.CharField()
    today = PresenceSerializer(many=True)
    recent = PresenceSerializer(many=True)
    events = PresenceEventSerializer(many=True)
