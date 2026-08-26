# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# No native geo libraries are needed: geofence maths is pure Python and psycopg
# ships as a binary wheel, so the slim image only wants curl for the healthcheck.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install --no-install-recommends -y \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/staticfiles \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health/ || exit 1

ENV DJANGO_SETTINGS_MODULE=config.settings.production

# ---------------------------------------------------------------------------
# Boot sequence: migrate, ensure the superuser exists, collect static files,
# then start Gunicorn.
#
# The superuser step is a real management command rather than an inline
# `shell -c` one-liner. Two reasons the old one-liner broke this image:
#   * it queried `username`, which this project's User model does not have -
#     email is USERNAME_FIELD - so every boot exited 1 with a FieldError;
#   * `createsuperuser`-style creation is not idempotent, so a redeploy over an
#     existing database would fail even once the field name was right.
# `ensure_superuser` reports and exits 0 when the admin already exists.
#
# $PORT is honoured for platforms that assign one (Render, Heroku, Fly).
# ---------------------------------------------------------------------------
CMD ["sh", "-c", \
    "python manage.py migrate --noinput && \
     python manage.py ensure_superuser --skip-if-unset && \
     python manage.py collectstatic --noinput && \
     exec gunicorn config.wsgi:application \
     --bind 0.0.0.0:${PORT:-8000} \
     --workers 3 \
     --timeout 60 \
     --access-logfile - \
     --error-logfile -"]
