.PHONY: help install dev-install up down migrate migrations run worker beat test test-fast lint format typecheck schema seed shell check

PY ?= python
MANAGE = $(PY) manage.py

help:
	@echo "install       install runtime dependencies"
	@echo "dev-install   install runtime + development dependencies"
	@echo "up/down       start/stop PostgreSQL and Redis via docker compose"
	@echo "migrate       apply migrations"
	@echo "migrations    create migrations"
	@echo "run           run the development server"
	@echo "worker/beat   run Celery"
	@echo "test          run the whole suite (needs PostgreSQL)"
	@echo "test-fast     run only the tests that need no database"
	@echo "lint/format   ruff / black"
	@echo "schema        regenerate docs/openapi.yaml"
	@echo "seed          create demo data"

install:
	$(PY) -m pip install -r requirements.txt

dev-install:
	$(PY) -m pip install -r requirements-dev.txt

up:
	docker compose up -d db redis

down:
	docker compose down

migrate:
	$(MANAGE) migrate

migrations:
	$(MANAGE) makemigrations

run:
	$(MANAGE) runserver 0.0.0.0:8000

worker:
	celery -A config worker --loglevel=info

beat:
	celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler

test:
	$(PY) -m pytest

test-fast:
	$(PY) -m pytest tests/test_state_machine.py tests/test_geo_math.py tests/test_geofence_validation.py::TestBoundingBoxValidation tests/test_geofence_evaluation.py::TestClassify -q

check:
	$(MANAGE) check --deploy

lint:
	ruff check .

format:
	black . && ruff check --fix .

typecheck:
	mypy .

schema:
	$(MANAGE) spectacular --file docs/openapi.yaml

seed:
	$(MANAGE) seed_demo_data --reset

shell:
	$(MANAGE) shell
