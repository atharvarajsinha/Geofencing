"""Account serializers."""
from __future__ import annotations

from typing import Any

from django.contrib.auth import authenticate
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User


class UserSerializer(serializers.ModelSerializer):
    """Public representation of an account."""

    organization_id = serializers.IntegerField(read_only=True)
    organization_name = serializers.CharField(
        source="organization.name", read_only=True, default=None
    )
    organization_timezone = serializers.CharField(
        source="organization.timezone", read_only=True, default=None
    )

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "name",
            "phone_number",
            "role",
            "organization_id",
            "organization_name",
            "organization_timezone",
            "is_active",
            "is_staff",
            "date_joined",
            "updated_at",
        )
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    """Email/password exchange for a JWT pair.

    Written explicitly rather than reusing ``TokenObtainPairSerializer`` so the
    response shape (tokens *and* the user object) is under our control and the
    failure message never distinguishes "unknown email" from "wrong password".
    """

    email = serializers.EmailField(write_only=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    default_error_messages = {
        "invalid_credentials": "Invalid email or password.",
        "inactive": "This account has been deactivated.",
        "inactive_organization": "Your organization has been deactivated.",
    }

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        request = self.context.get("request")
        user = authenticate(
            request=request,
            username=attrs["email"].strip().lower(),
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError(
                {"detail": [self.error_messages["invalid_credentials"]]}, code="authentication"
            )
        if not user.is_active:
            raise serializers.ValidationError(
                {"detail": [self.error_messages["inactive"]]}, code="authentication"
            )
        if user.organization_id and not user.organization.is_active:
            raise serializers.ValidationError(
                {"detail": [self.error_messages["inactive_organization"]]},
                code="authentication",
            )

        refresh = RefreshToken.for_user(user)
        refresh["role"] = user.role
        refresh["organization_id"] = user.organization_id

        attrs["user"] = user
        attrs["refresh"] = str(refresh)
        attrs["access"] = str(refresh.access_token)
        return attrs

    def to_representation(self, instance: dict[str, Any]) -> dict[str, Any]:
        return {
            "access": instance["access"],
            "refresh": instance["refresh"],
            "user": UserSerializer(instance["user"]).data,
        }


class TokenPairResponseSerializer(serializers.Serializer):
    """Documentation-only schema for the login response."""

    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()


class ClaimEnrichedTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Kept for parity with SimpleJWT tooling (e.g. management commands)."""

    @classmethod
    def get_token(cls, user: User):  # pragma: no cover - thin override
        token = super().get_token(user)
        token["role"] = user.role
        token["organization_id"] = user.organization_id
        return token
