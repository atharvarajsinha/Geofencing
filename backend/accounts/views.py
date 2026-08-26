"""Authentication and account API.

Views stay thin: credential checking lives in the serializer/authentication
backend, tenancy filtering in selectors.
"""
from __future__ import annotations

from typing import Any

from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from accounts import selectors
from accounts.models import User
from accounts.permissions import IsOrganizationAdmin, IsSelfOrOrganizationAdmin
from accounts.serializers import (
    LoginSerializer,
    TokenPairResponseSerializer,
    UserSerializer,
)
from common.pagination import DefaultPagination
from common.throttling import AnonymousLoginThrottle


@extend_schema(tags=["auth"])
class LoginView(APIView):
    """Exchange email + password for an access/refresh token pair."""

    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = (AnonymousLoginThrottle,)
    serializer_class = LoginSerializer

    @extend_schema(
        request=LoginSerializer,
        responses={200: TokenPairResponseSerializer},
        summary="Log in",
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(tags=["auth"], summary="Refresh an access token")
class RefreshTokenView(TokenRefreshView):
    """Rotate the refresh token and issue a new access token."""

    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = (AnonymousLoginThrottle,)


@extend_schema(tags=["auth"])
class MeView(generics.RetrieveAPIView):
    """The authenticated caller's own profile."""

    serializer_class = UserSerializer
    throttle_scope = "read"

    def get_object(self) -> User:
        return (
            User.objects.select_related("organization").get(pk=self.request.user.pk)
        )


class UserFilterSet(filters.FilterSet):
    role = filters.CharFilter(field_name="role", lookup_expr="iexact")
    is_active = filters.BooleanFilter(field_name="is_active")
    search = filters.CharFilter(method="filter_search")

    class Meta:
        model = User
        fields = ("role", "is_active")

    def filter_search(self, queryset, name: str, value: str):
        return queryset.filter(name__icontains=value) | queryset.filter(
            email__icontains=value
        )


@extend_schema(tags=["auth"])
class OrganizationUserListView(generics.ListAPIView):
    """Members of the caller's organization (admin only).

    The admin dashboard needs the full roster to report "total users" and to
    show members who have never sent a location update.
    """

    serializer_class = UserSerializer
    permission_classes = (IsOrganizationAdmin,)
    # Only used for schema introspection; get_queryset() is authoritative.
    queryset = User.objects.none()
    pagination_class = DefaultPagination
    filterset_class = UserFilterSet
    ordering_fields = ("name", "email", "date_joined")
    ordering = ("name",)
    throttle_scope = "read"

    def get_queryset(self):
        return selectors.visible_users_for(self.request.user)


@extend_schema(tags=["auth"])
class UserDetailView(generics.RetrieveAPIView):
    """A single account, restricted to self or same-organization admins."""

    serializer_class = UserSerializer
    permission_classes = (IsSelfOrOrganizationAdmin,)
    queryset = User.objects.none()
    throttle_scope = "read"

    def get_queryset(self):
        return selectors.visible_users_for(self.request.user)
