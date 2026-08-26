from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Accounts"

    def ready(self) -> None:
        # Fail fast on a misconfigured deployment rather than halfway through
        # the first location update.
        from common.conf import geo_conf

        geo_conf.check()
