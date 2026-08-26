"""Organization serializers."""
from __future__ import annotations

from rest_framework import serializers

from organizations.models import Organization


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = (
            "id",
            "name",
            "code",
            "timezone",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class OrganizationWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ("name", "code", "timezone", "is_active")
