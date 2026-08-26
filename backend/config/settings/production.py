"""Production settings.

Assumes TLS termination in front of the application (nginx / load balancer)
that sets ``X-Forwarded-Proto``.
"""
from __future__ import annotations

from config.settings.base import *  # noqa: F401,F403
from config.settings.base import env

DEBUG = False

# Fail loudly instead of silently serving with a permissive host list.
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

# --------------------------------------------------------------------------
# HTTPS / transport security
# --------------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31_536_000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# --------------------------------------------------------------------------
# Cookies
#
# The API itself is stateless (JWT in the Authorization header); these cover
# the Django admin and the session/CSRF cookies it relies on.
# --------------------------------------------------------------------------
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# --------------------------------------------------------------------------
# CORS is an allow-list only. An empty list means "same origin only".
# --------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=CORS_ALLOWED_ORIGINS)

ADMIN_URL = env("DJANGO_ADMIN_URL", default="admin/")
