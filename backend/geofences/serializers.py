"""Geofence serializers.

The wire format is plain numbers, which is both what a map widget produces and
what the model stores: a centre plus radius for a CIRCLE, or the four bounding
edges for a RECTANGLE. Reads return the same shape plus the thresholds the
backend actually applies.
"""
from __future__ import annotations

from typing import Any

from rest_framework import serializers

from geofences.enums import GeofenceType
from geofences.models import Geofence

#: The four numbers that define a RECTANGLE.
BOUNDS_FIELDS = ("min_latitude", "max_latitude", "min_longitude", "max_longitude")


class GeofenceSerializer(serializers.ModelSerializer):
    """Read representation."""

    type = serializers.CharField(source="geofence_type", read_only=True)
    #: Representative point: the circle centre, or the centre of the rectangle.
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    effective_thresholds = serializers.SerializerMethodField()

    class Meta:
        model = Geofence
        fields = (
            "id",
            "organization_id",
            "name",
            "type",
            # Circle
            "center_latitude",
            "center_longitude",
            "radius",
            # Rectangle, and the derived envelope of a circle
            "min_latitude",
            "max_latitude",
            "min_longitude",
            "max_longitude",
            # Convenience aliases for map widgets
            "latitude",
            "longitude",
            # Hysteresis
            "entry_radius",
            "exit_radius",
            "required_inside_readings",
            "required_outside_readings",
            "stale_after_seconds",
            "effective_thresholds",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_latitude(self, obj: Geofence) -> float | None:
        return obj.latitude

    def get_longitude(self, obj: Geofence) -> float | None:
        return obj.longitude

    def get_effective_thresholds(self, obj: Geofence) -> dict[str, Any]:
        """What the evaluator will actually use, defaults resolved."""
        return {
            "entry_threshold_m": obj.effective_entry_threshold_m,
            "exit_threshold_m": obj.effective_exit_threshold_m,
            "required_inside_readings": obj.effective_required_inside_readings,
            "required_outside_readings": obj.effective_required_outside_readings,
            "stale_after_seconds": obj.effective_stale_after_seconds,
        }


class GeofenceWriteSerializer(serializers.Serializer):
    """Input shape for create/update.

    Only structural checks live here; geometric and business validation is
    performed by :mod:`geofences.validators` from inside the service so that
    the exact same rules apply to any other caller (admin site, management
    commands, data imports).
    """

    name = serializers.CharField(max_length=150)
    type = serializers.ChoiceField(choices=GeofenceType.choices)

    # CIRCLE
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)
    radius = serializers.FloatField(required=False, allow_null=True)

    # RECTANGLE
    min_latitude = serializers.FloatField(required=False, allow_null=True)
    max_latitude = serializers.FloatField(required=False, allow_null=True)
    min_longitude = serializers.FloatField(required=False, allow_null=True)
    max_longitude = serializers.FloatField(required=False, allow_null=True)

    entry_radius = serializers.FloatField(required=False, allow_null=True, min_value=0)
    exit_radius = serializers.FloatField(required=False, allow_null=True, min_value=0)
    required_inside_readings = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=20
    )
    required_outside_readings = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=20
    )
    stale_after_seconds = serializers.IntegerField(
        required=False, allow_null=True, min_value=30, max_value=86_400
    )
    is_active = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        partial = getattr(self, "partial", False)
        geofence_type = attrs.get("type")

        if not partial and geofence_type == GeofenceType.CIRCLE:
            missing = [
                field
                for field in ("latitude", "longitude", "radius")
                if attrs.get(field) is None
            ]
            if missing:
                raise serializers.ValidationError(
                    {field: ["Required for a CIRCLE geofence."] for field in missing}
                )
            supplied_bounds = [
                field for field in BOUNDS_FIELDS if attrs.get(field) is not None
            ]
            if supplied_bounds:
                raise serializers.ValidationError(
                    {
                        field: [
                            "Not allowed for a CIRCLE geofence; the bounding box is "
                            "derived from the centre and radius."
                        ]
                        for field in supplied_bounds
                    }
                )

        if not partial and geofence_type == GeofenceType.RECTANGLE:
            missing = [
                field for field in BOUNDS_FIELDS if attrs.get(field) is None
            ]
            if missing:
                raise serializers.ValidationError(
                    {field: ["Required for a RECTANGLE geofence."] for field in missing}
                )
            if any(
                attrs.get(field) is not None
                for field in ("latitude", "longitude", "radius")
            ):
                raise serializers.ValidationError(
                    {
                        "detail": [
                            "latitude/longitude/radius are not allowed for a "
                            "RECTANGLE geofence."
                        ]
                    }
                )
        return attrs

    def to_service_kwargs(self) -> dict[str, Any]:
        """Map the wire payload onto the service signature."""
        data = dict(self.validated_data)
        if "type" in data:
            data["geofence_type"] = data.pop("type")
        return data
