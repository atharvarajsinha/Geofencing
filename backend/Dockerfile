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
# Run migrations, create superuser if it doesn't exist, collect static files,
# then start Gunicorn.
# ---------------------------------------------------------------------------
CMD ["sh", "-c", \
    "python manage.py migrate --noinput && \
     python manage.py shell -c \"\
from django.contrib.auth import get_user_model; \
import os; \
User = get_user_model(); \
username = os.environ.get('DJANGO_SUPERUSER_USERNAME'); \
email = os.environ.get('DJANGO_SUPERUSER_EMAIL'); \
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD'); \
\
print('Checking Django superuser...'); \
\
user = User.objects.filter(username=username).first() if username else None; \
\
User.objects.create_superuser(username=username, email=email, password=password) \
if username and email and password and not user else \
print('Superuser already exists or credentials are missing.'); \
\" && \
     python manage.py collectstatic --noinput && \
     gunicorn config.wsgi:application \
     --bind 0.0.0.0:8000 \
     --workers 3 \
     --timeout 60 \
     --access-logfile - \
     --error-logfile -"]