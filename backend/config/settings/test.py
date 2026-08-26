"""Settings used by the automated test suite.

A real PostgreSQL database is required (no PostGIS): the suite exercises the
constraints and the concurrency behaviour, which SQLite cannot reproduce.
Geofence evaluation itself is pure Python and needs no database at all.
"""
from __future__ import annotations

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "insecure-test-key")
os.environ.setdefault("DJANGO_DEBUG", "False")
os.environ.setdefault(
    "DATABASE_URL", "postgres://geofencing:geofencing@localhost:5432/geofencing"
)

from config.settings.base import *  # noqa: E402,F401,F403
from config.settings.base import GEOFENCING, REST_FRAMEWORK  # noqa: E402

DEBUG = False
ALLOWED_HOSTS = ["*"]

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-cache",
    }
}

# Tasks execute inline; no broker needed for the suite.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

# Throttling is exercised by a dedicated test that re-enables it explicitly.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {
        "auth": "1000/min",
        "location_update": "1000/min",
        "read": "1000/min",
        "write": "1000/min",
    },
}

# Deterministic thresholds so the tests read like the documentation.
GEOFENCING = {
    **GEOFENCING,
    "REQUIRED_INSIDE_READINGS": 2,
    "REQUIRED_OUTSIDE_READINGS": 3,
    "STALE_AFTER_SECONDS": 300,
    "MAX_ACCEPTABLE_ACCURACY_M": 50.0,
    "STREAK_MAX_GAP_SECONDS": 300,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "common.logging.RequestIDFilter"}},
    "handlers": {"null": {"class": "logging.NullHandler"}},
    "root": {"handlers": ["null"], "level": "CRITICAL"},
}
