from __future__ import annotations

from django.urls import path

from accounts.views import (
    LoginView,
    MeView,
    OrganizationUserListView,
    RefreshTokenView,
    UserDetailView,
)

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshTokenView.as_view(), name="refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("users/", OrganizationUserListView.as_view(), name="user-list"),
    path("users/<int:pk>/", UserDetailView.as_view(), name="user-detail"),
]
