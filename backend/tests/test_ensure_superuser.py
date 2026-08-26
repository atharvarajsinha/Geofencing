"""The deploy-time superuser bootstrap.

This command runs on every container boot, so the property that matters most is
that it is idempotent and never fails a redeploy.
"""
from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.enums import UserRole
from accounts.models import User
from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

EMAIL = "root@example.com"
PASSWORD = "S3cure-Deploy-Passw0rd!"


@pytest.fixture
def credentials(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", EMAIL)
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", PASSWORD)
    monkeypatch.delenv("DJANGO_SUPERUSER_NAME", raising=False)


class TestCreation:
    def test_creates_the_super_admin(self, credentials, capsys):
        call_command("ensure_superuser")

        user = User.objects.get(email=EMAIL)
        assert user.role == UserRole.ADMIN
        assert user.is_staff and user.is_superuser and user.is_active
        assert user.check_password(PASSWORD)
        # No organization: this is the platform operator.
        assert user.organization_id is None
        assert user.is_platform_admin

    def test_name_defaults_to_the_email_local_part(self, credentials):
        call_command("ensure_superuser")
        assert User.objects.get(email=EMAIL).name == "root"

    def test_explicit_name_is_used(self, credentials, monkeypatch):
        monkeypatch.setenv("DJANGO_SUPERUSER_NAME", "Site Operator")
        call_command("ensure_superuser")
        assert User.objects.get(email=EMAIL).name == "Site Operator"

    def test_email_is_normalised(self, monkeypatch):
        monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "  ROOT@Example.COM  ")
        monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", PASSWORD)
        call_command("ensure_superuser")
        assert User.objects.filter(email=EMAIL).exists()

    def test_the_password_is_never_echoed(self, credentials, capsys):
        call_command("ensure_superuser")
        assert PASSWORD not in capsys.readouterr().out


class TestIdempotency:
    """A redeploy must not fail. This is the whole point of the command."""

    def test_running_twice_is_a_no_op(self, credentials, capsys):
        call_command("ensure_superuser")
        capsys.readouterr()

        call_command("ensure_superuser")  # must not raise

        assert User.objects.filter(email=EMAIL).count() == 1
        assert "already exists" in capsys.readouterr().out

    def test_a_different_existing_admin_is_reported_not_duplicated(
        self, credentials, capsys
    ):
        UserFactory(
            email="someone.else@example.com",
            role=UserRole.ADMIN,
            organization=None,
            is_staff=True,
            is_superuser=True,
        )

        call_command("ensure_superuser")  # must not raise

        # The single-ADMIN constraint is respected: still exactly one.
        assert User.objects.admins().count() == 1
        assert not User.objects.filter(email=EMAIL).exists()
        assert "set_super_admin" in capsys.readouterr().out

    def test_an_existing_non_admin_account_is_left_alone(
        self, credentials, organization, capsys
    ):
        UserFactory(email=EMAIL, organization=organization, role=UserRole.USER)

        call_command("ensure_superuser")  # must not raise

        user = User.objects.get(email=EMAIL)
        assert user.role == UserRole.USER, "must not silently promote an account"
        assert "set_super_admin" in capsys.readouterr().out


class TestConfiguration:
    def test_missing_credentials_is_an_error_by_default(self, monkeypatch):
        monkeypatch.delenv("DJANGO_SUPERUSER_EMAIL", raising=False)
        monkeypatch.delenv("DJANGO_SUPERUSER_PASSWORD", raising=False)

        with pytest.raises(CommandError) as error:
            call_command("ensure_superuser")
        assert "DJANGO_SUPERUSER_EMAIL" in str(error.value)

    def test_missing_password_alone_is_reported(self, monkeypatch):
        monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", EMAIL)
        monkeypatch.delenv("DJANGO_SUPERUSER_PASSWORD", raising=False)

        with pytest.raises(CommandError) as error:
            call_command("ensure_superuser")
        assert "DJANGO_SUPERUSER_PASSWORD" in str(error.value)
        assert "DJANGO_SUPERUSER_EMAIL" not in str(error.value)

    def test_skip_if_unset_makes_it_a_no_op(self, monkeypatch, capsys):
        monkeypatch.delenv("DJANGO_SUPERUSER_EMAIL", raising=False)
        monkeypatch.delenv("DJANGO_SUPERUSER_PASSWORD", raising=False)

        call_command("ensure_superuser", "--skip-if-unset")  # must not raise

        assert not User.objects.exists()
        assert "Skipping" in capsys.readouterr().out

    def test_flags_override_the_environment(self, credentials):
        call_command("ensure_superuser", "--email", "flag@example.com", "--name", "Flag")
        assert User.objects.get(email="flag@example.com").name == "Flag"

    def test_an_invalid_email_fails_loudly(self, monkeypatch):
        monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "not-an-email")
        monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", PASSWORD)

        with pytest.raises(CommandError):
            call_command("ensure_superuser")
