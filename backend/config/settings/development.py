"""Local development settings."""
from __future__ import annotations

import os

# Developer convenience only: never rely on these in a deployed environment.
os.environ.setdefault("DJANGO_SECRET_KEY", "insecure-development-key-change-me")
os.environ.setdefault("DJANGO_DEBUG", "True")
os.environ.setdefault(
    "DATABASE_URL", "postgres://geofencing:geofencing@localhost:5432/geofencing"
)

from config.settings.base import *  # noqa: E402,F401,F403
from config.settings.base import GEOFENCING, REST_FRAMEWORK, env  # noqa: E402

DEBUG = True
ALLOWED_HOSTS = ["*"]

# The PWA typically runs on the Next.js dev server.
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "https://h1gf8wxf-3000.inc1.devtunnels.ms",
]
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = list(CORS_ALLOWED_ORIGINS)

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (
    "common.renderers.EnvelopeJSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
)

# Redis is optional locally. Without it the API still works: throttle counters
# just live in the process instead of a shared cache. Celery still needs a real
# broker, so set CACHE_URL/REDIS_URL once Redis is running.
if not env("CACHE_URL", default="") and not env("REDIS_URL", default=""):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "geofencing-dev",
        }
    }

# Faster feedback while testing the state machine by hand.
GEOFENCING["STALE_AFTER_SECONDS"] = int(os.environ.get("STALE_AFTER_SECONDS", 180))

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
