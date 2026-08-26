"""Base settings shared by every environment.

Every value that differs between deployments is read from the environment.
No secret has a usable default outside of DEBUG environments.
"""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# Read a local .env file when present. Deployments normally inject real
# environment variables instead and the file is simply absent.
environ.Env.read_env(BASE_DIR / ".env")

# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

# --------------------------------------------------------------------------
# Applications
# --------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "django_celery_beat",
]

LOCAL_APPS = [
    "common",
    "accounts",
    "organizations",
    "geofences",
    "locations",
    "presence",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "common.middleware.RequestIDMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------------------------------
# Database (plain PostgreSQL)
#
# This project has no GeoDjango/PostGIS/GDAL dependency. Geofences are stored
# as ordinary float columns (a centre plus radius, or a lat/lon bounding box)
# and every geographic decision is made in Python by common.utils.geo, so a
# stock PostgreSQL server and the psycopg wheel are all that is required.
# --------------------------------------------------------------------------
DATABASES = {
    "default": {
        **env.db_url("DATABASE_URL"),
        "ENGINE": "django.db.backends.postgresql",
        "CONN_MAX_AGE": env.int("DATABASE_CONN_MAX_AGE", default=60),
        "CONN_HEALTH_CHECKS": True,
        "ATOMIC_REQUESTS": False,
    }
}

# --------------------------------------------------------------------------
# Password validation / i18n
# --------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("DJANGO_TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# --------------------------------------------------------------------------
# Django REST Framework
# --------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "common.pagination.DefaultPagination",
    "PAGE_SIZE": env.int("API_PAGE_SIZE", default=25),
    "DEFAULT_RENDERER_CLASSES": ("common.renderers.EnvelopeJSONRenderer",),
    "EXCEPTION_HANDLER": "common.exceptions.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Fail-open, keyed by user rather than IP. See common/throttling.py.
    "DEFAULT_THROTTLE_CLASSES": ("common.throttling.UserScopedRateThrottle",),
    "DEFAULT_THROTTLE_RATES": {
        "auth": env("THROTTLE_RATE_AUTH", default="20/min"),
        "location_update": env("THROTTLE_RATE_LOCATION_UPDATE", default="60/min"),
        "read": env("THROTTLE_RATE_READ", default="240/min"),
        "write": env("THROTTLE_RATE_WRITE", default="60/min"),
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=30)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": env("JWT_SIGNING_KEY", default=SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Geofencing Presence API",
    "DESCRIPTION": (
        "Backend API for a PWA based geofencing attendance/presence system. "
        "The backend is the sole authority on presence status; clients only "
        "submit raw GPS observations."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api",
    "SERVERS": [{"url": env("API_PUBLIC_URL", default="http://localhost:8000")}],
    # Several serializers expose the same choice sets; name them once.
    "ENUM_NAME_OVERRIDES": {
        "PresenceStatusEnum": "presence.enums.PresenceStatus.choices",
        "PresenceEventTypeEnum": "presence.enums.PresenceEventType.choices",
        "GeofenceTypeEnum": "geofences.enums.GeofenceType.choices",
        "AnomalyTypeEnum": "locations.enums.AnomalyType.choices",
        "AnomalySeverityEnum": "locations.enums.AnomalySeverity.choices",
        "UserRoleEnum": "accounts.enums.UserRole.choices",
    },
}

# --------------------------------------------------------------------------
# CORS (the PWA is served from a different origin)
# --------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = env.bool("CORS_ALLOW_CREDENTIALS", default=False)
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# --------------------------------------------------------------------------
# Request size limits (location payloads are tiny; anything large is abuse)
# --------------------------------------------------------------------------
DATA_UPLOAD_MAX_MEMORY_SIZE = env.int("DATA_UPLOAD_MAX_MEMORY_SIZE", default=256 * 1024)
DATA_UPLOAD_MAX_NUMBER_FIELDS = 200
FILE_UPLOAD_MAX_MEMORY_SIZE = env.int("FILE_UPLOAD_MAX_MEMORY_SIZE", default=1024 * 1024)

# --------------------------------------------------------------------------
# Cache / Celery / Redis
# --------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", default="redis://127.0.0.1:6379/0")

# Throttle counters live in the cache, so a shared cache is required for rate
# limiting to mean anything across processes. Development falls back to
# local memory when no cache is configured (see settings/development.py).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("CACHE_URL", default=REDIS_URL),
        "KEY_PREFIX": "geofencing",
    }
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 240
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

CELERY_BEAT_SCHEDULE = {
    "detect-stale-presence": {
        "task": "presence.tasks.detect_stale_presence",
        "schedule": env.int("STALE_SCAN_INTERVAL_SECONDS", default=60),
        "options": {"expires": 55},
    },
    "close-abandoned-presence-days": {
        "task": "presence.tasks.close_abandoned_presence_days",
        "schedule": 3600,
        "options": {"expires": 1800},
    },
    "purge-expired-location-history": {
        "task": "locations.tasks.purge_expired_location_history",
        "schedule": 24 * 3600,
    },
    "purge-expired-presence-events": {
        "task": "presence.tasks.purge_expired_presence_events",
        "schedule": 24 * 3600,
    },
}

# --------------------------------------------------------------------------
# Domain tunables
#
# Everything the geofence/presence algorithms depend on lives here so that no
# magic number is buried in the code. ``common.conf.geo_conf`` is the typed
# accessor; docs/GEOFENCE_ALGORITHM.md explains the defaults.
# --------------------------------------------------------------------------
GEOFENCING = {
    # -- Geometry ---------------------------------------------------------
    "MIN_RADIUS_M": env.float("MIN_RADIUS_M", default=10.0),
    "MAX_RADIUS_M": env.float("MAX_RADIUS_M", default=50_000.0),
    # Upper bound on the area of any single geofence (circle envelope or
    # rectangle), as a guard against a mistyped coordinate covering a country.
    "MAX_GEOFENCE_AREA_KM2": env.float("MAX_GEOFENCE_AREA_KM2", default=500.0),
    # Default hysteresis band applied when an admin does not supply one.
    "DEFAULT_ENTRY_BUFFER_M": env.float("DEFAULT_ENTRY_BUFFER_M", default=0.0),
    "DEFAULT_EXIT_BUFFER_M": env.float("DEFAULT_EXIT_BUFFER_M", default=40.0),
    # -- GPS accuracy -----------------------------------------------------
    "MAX_ACCEPTABLE_ACCURACY_M": env.float("MAX_ACCEPTABLE_ACCURACY_M", default=50.0),
    "HARD_REJECT_ACCURACY_M": env.float("HARD_REJECT_ACCURACY_M", default=1000.0),
    # Fraction of the reported accuracy radius used as the uncertainty margin.
    "ACCURACY_MARGIN_FACTOR": env.float("ACCURACY_MARGIN_FACTOR", default=1.0),
    # Never let one absurd accuracy value make every verdict UNCERTAIN forever.
    "ACCURACY_MARGIN_CAP_M": env.float("ACCURACY_MARGIN_CAP_M", default=150.0),
    # -- Hysteresis / debouncing ------------------------------------------
    "REQUIRED_INSIDE_READINGS": env.int("REQUIRED_INSIDE_READINGS", default=2),
    "REQUIRED_OUTSIDE_READINGS": env.int("REQUIRED_OUTSIDE_READINGS", default=3),
    # Two readings hours apart are not a streak; reset the counters when the
    # gap between consecutive readings exceeds this value.
    "STREAK_MAX_GAP_SECONDS": env.int("STREAK_MAX_GAP_SECONDS", default=300),
    # -- Freshness --------------------------------------------------------
    "STALE_AFTER_SECONDS": env.int("STALE_AFTER_SECONDS", default=300),
    "MAX_LOCATION_AGE_SECONDS": env.int("MAX_LOCATION_AGE_SECONDS", default=3600),
    "MAX_CLOCK_SKEW_SECONDS": env.int("MAX_CLOCK_SKEW_SECONDS", default=120),
    # -- Anomaly detection ------------------------------------------------
    "MAX_PLAUSIBLE_SPEED_KMH": env.float("MAX_PLAUSIBLE_SPEED_KMH", default=300.0),
    "JUMP_DISTANCE_M": env.float("JUMP_DISTANCE_M", default=5_000.0),
    "JUMP_WINDOW_SECONDS": env.int("JUMP_WINDOW_SECONDS", default=60),
    "STATIONARY_TOLERANCE_M": env.float("STATIONARY_TOLERANCE_M", default=1.0),
    "STATIONARY_MIN_SECONDS": env.int("STATIONARY_MIN_SECONDS", default=1800),
    "STATIONARY_MIN_READINGS": env.int("STATIONARY_MIN_READINGS", default=10),
    "MAX_UPDATES_PER_MINUTE": env.int("MAX_UPDATES_PER_MINUTE", default=30),
    # -- Client guidance ---------------------------------------------------
    "RECOMMENDED_PING_INTERVAL_SECONDS": env.int(
        "RECOMMENDED_PING_INTERVAL_SECONDS", default=60
    ),
    # -- Retention (privacy) -----------------------------------------------
    "LOCATION_HISTORY_RETENTION_DAYS": env.int("LOCATION_HISTORY_RETENTION_DAYS", default=30),
    "PRESENCE_EVENT_RETENTION_DAYS": env.int("PRESENCE_EVENT_RETENTION_DAYS", default=365),
    "ANOMALY_RETENTION_DAYS": env.int("ANOMALY_RETENTION_DAYS", default=90),
    # -- Safety rails --------------------------------------------------------
    "MAX_GEOFENCES_EVALUATED_PER_UPDATE": env.int(
        "MAX_GEOFENCES_EVALUATED_PER_UPDATE", default=50
    ),
}

# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
LOG_LEVEL = env("DJANGO_LOG_LEVEL", default="INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s",
        },
    },
    "filters": {
        "request_id": {"()": "common.logging.RequestIDFilter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["request_id"],
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        "geofencing": {"level": LOG_LEVEL, "handlers": ["console"], "propagate": False},
    },
}
