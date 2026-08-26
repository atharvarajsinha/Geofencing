"""Authentication, roles and the response envelope."""
from __future__ import annotations

import pytest
from django.urls import reverse

from accounts import selectors, services
from accounts.enums import UserRole
from accounts.models import User
from common.exceptions import ValidationFailed
from tests.factories import DEFAULT_PASSWORD, UserFactory

pytestmark = pytest.mark.django_db


class TestLogin:
    def test_login_returns_tokens_and_the_user(self, api_client, user):
        response = api_client.post(
            reverse("auth:login"),
            {"email": user.email, "password": DEFAULT_PASSWORD},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["access"]
        assert body["data"]["refresh"]
        assert body["data"]["user"]["email"] == user.email
        assert "password" not in body["data"]["user"]

    def test_email_is_case_insensitive(self, api_client, user):
        response = api_client.post(
            reverse("auth:login"),
            {"email": user.email.upper(), "password": DEFAULT_PASSWORD},
        )
        assert response.status_code == 200

    def test_wrong_password_is_rejected(self, api_client, user):
        response = api_client.post(
            reverse("auth:login"), {"email": user.email, "password": "wrong-password"}
        )
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False
        assert "errors" in body

    def test_unknown_email_gives_the_same_error(self, api_client, user):
        unknown = api_client.post(
            reverse("auth:login"),
            {"email": "nobody@example.com", "password": DEFAULT_PASSWORD},
        ).json()
        wrong = api_client.post(
            reverse("auth:login"), {"email": user.email, "password": "nope-nope-nope"}
        ).json()
        # Identical messages: the API must not confirm which emails exist.
        assert unknown["errors"] == wrong["errors"]

    def test_inactive_user_cannot_log_in(self, api_client, user):
        user.is_active = False
        user.save(update_fields=["is_active"])
        response = api_client.post(
            reverse("auth:login"), {"email": user.email, "password": DEFAULT_PASSWORD}
        )
        assert response.status_code == 400

    def test_missing_fields_are_reported_per_field(self, api_client):
        response = api_client.post(reverse("auth:login"), {})
        assert response.status_code == 400
        errors = response.json()["errors"]
        assert "email" in errors and "password" in errors


class TestRefresh:
    def test_refresh_issues_a_new_access_token(self, api_client, user):
        tokens = api_client.post(
            reverse("auth:login"),
            {"email": user.email, "password": DEFAULT_PASSWORD},
        ).json()["data"]

        response = api_client.post(
            reverse("auth:refresh"), {"refresh": tokens["refresh"]}
        )
        assert response.status_code == 200
        assert response.json()["data"]["access"]

    def test_garbage_refresh_token_is_rejected(self, api_client):
        response = api_client.post(reverse("auth:refresh"), {"refresh": "not-a-token"})
        assert response.status_code == 401


class TestMe:
    def test_requires_authentication(self, api_client):
        assert api_client.get(reverse("auth:me")).status_code == 401

    def test_returns_the_caller(self, api_client, user):
        tokens = api_client.post(
            reverse("auth:login"),
            {"email": user.email, "password": DEFAULT_PASSWORD},
        ).json()["data"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        response = api_client.get(reverse("auth:me"))
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["email"] == user.email
        assert data["organization_id"] == user.organization_id
        assert data["organization_timezone"] == "UTC"

    def test_bearer_token_of_another_user_returns_that_user_only(
        self, api_client, user, other_user
    ):
        tokens = api_client.post(
            reverse("auth:login"),
            {"email": other_user.email, "password": DEFAULT_PASSWORD},
        ).json()["data"]
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        assert api_client.get(reverse("auth:me")).json()["data"]["email"] == other_user.email


class TestUserDirectory:
    def test_members_cannot_list_the_directory(self, user_client):
        assert user_client.get(reverse("auth:user-list")).status_code == 403

    def test_admins_see_only_their_organization(
        self, admin_client, organization, other_organization
    ):
        UserFactory(organization=organization, email="inside@example.com")
        UserFactory(organization=other_organization, email="outside@example.com")

        response = admin_client.get(reverse("auth:user-list"))
        assert response.status_code == 200
        emails = {row["email"] for row in response.json()["data"]["results"]}
        assert "inside@example.com" in emails
        assert "outside@example.com" not in emails

    def test_a_user_can_read_their_own_record(self, user_client, user):
        response = user_client.get(reverse("auth:user-detail", args=[user.pk]))
        assert response.status_code == 200

    def test_a_user_cannot_read_somebody_else(self, user_client, other_user):
        response = user_client.get(reverse("auth:user-detail", args=[other_user.pk]))
        assert response.status_code == 404


class TestRoles:
    def test_there_are_only_two_roles(self):
        assert [choice[0] for choice in UserRole.choices] == ["ADMIN", "USER"]

    def test_platform_admin_has_no_organization(self, platform_admin):
        assert platform_admin.is_admin is True
        assert platform_admin.is_platform_admin is True
        assert platform_admin.organization_id is None

    def test_organization_admin_is_not_a_platform_admin(self, admin_user):
        assert admin_user.is_admin is True
        assert admin_user.is_organization_admin is True
        assert admin_user.is_platform_admin is False

    def test_regular_user_is_neither(self, user):
        assert user.is_admin is False
        assert user.is_organization_admin is False
        assert user.is_platform_admin is False

    def test_new_accounts_default_to_user(self, organization):
        created = services.create_user(
            email="fresh@example.com",
            name="Fresh",
            password=DEFAULT_PASSWORD,
            organization=organization,
        )
        assert created.role == UserRole.USER


class TestSingleSuperAdmin:
    """Exactly one ADMIN exists; everybody else is a USER."""

    def test_a_second_admin_cannot_be_created(self, admin_user, organization):
        with pytest.raises(ValidationFailed):
            services.create_user(
                email="second-admin@example.com",
                name="Second Admin",
                password=DEFAULT_PASSWORD,
                organization=organization,
                role=UserRole.ADMIN,
            )
        assert User.objects.admins().count() == 1

    def test_a_user_cannot_be_promoted_alongside_the_admin(self, admin_user, user):
        with pytest.raises(ValidationFailed):
            services.update_user(user=user, role=UserRole.ADMIN)
        user.refresh_from_db()
        assert user.role == UserRole.USER

    def test_the_database_refuses_a_second_admin(self, admin_user, organization):
        """The invariant survives code that bypasses the service layer."""
        from django.db import IntegrityError, transaction

        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.create(
                email="sneaky@example.com",
                name="Sneaky",
                role=UserRole.ADMIN,
                organization=organization,
            )

    def test_transferring_the_role_demotes_the_incumbent(self, admin_user, user):
        services.transfer_admin(to_user=user)

        user.refresh_from_db()
        admin_user.refresh_from_db()
        assert user.role == UserRole.ADMIN
        assert admin_user.role == UserRole.USER
        assert User.objects.admins().count() == 1
        assert selectors.get_admin().pk == user.pk

    def test_transferring_to_the_incumbent_is_a_no_op(self, admin_user):
        services.transfer_admin(to_user=admin_user)
        assert User.objects.admins().count() == 1

    def test_a_platform_admin_cannot_be_demoted_into_a_stateless_user(
        self, platform_admin, user
    ):
        """Demoting an organization-less admin would break the tenancy check."""
        with pytest.raises(ValidationFailed):
            services.transfer_admin(to_user=user)
        platform_admin.refresh_from_db()
        assert platform_admin.role == UserRole.ADMIN
