# Development setup

One thing must be true before the project runs: a **PostgreSQL server** is
reachable. That is all.

There is no PostGIS extension to install and no native GEOS/GDAL/PROJ libraries
to locate: geofences are stored as ordinary float columns and every geographic
comparison runs in Python (`common/utils/geo.py`). On Windows in particular this
removes the whole "GeoDjango cannot find geos_c.dll" class of problem.

---

## 1. Database

### Option A - Docker (fastest, nothing to install)

```bash
docker compose up -d db redis
```

Gives PostgreSQL 16 on `localhost:5432` and Redis on `6379`, matching the
`DATABASE_URL` in `.env.example`. If you already run PostgreSQL on 5432, change
the published port to `5433:5432` and update `DATABASE_URL`.

### Option B - an existing PostgreSQL install (Windows, pgAdmin, no Docker)

Any stock PostgreSQL 13+ works. Create the role and database by running
[`scripts/setup_local_db.sql`](../scripts/setup_local_db.sql) in pgAdmin as the
`postgres` superuser - two statements, plus an ownership grant.

The one error that still comes up:

| `migrate` says | Cause | Fix (as `postgres`, connected to `geofencing`) |
|---|---|---|
| `permission denied for schema public` | PostgreSQL 15+ restricts the `public` schema to the database owner | `ALTER DATABASE geofencing OWNER TO geofencing;` and `GRANT USAGE, CREATE ON SCHEMA public TO geofencing;` |

Point `.env` at it:

```
DATABASE_URL=postgres://geofencing:geofencing@localhost:5432/geofencing
```

The quickest variant, if you would rather not create a role, is the superuser
you set up during installation:

```
DATABASE_URL=postgres://postgres:<your-password>@localhost:5432/geofencing
```

That is fine on a development machine and nowhere else.

> **Note on the URL scheme:** `postgres://` and `postgresql://` both work.
> A leftover `postgis://` also still resolves, because `django-environ` maps it
> to the same driver, but the engine is pinned to
> `django.db.backends.postgresql` in settings either way.

> **Redis** backs two things: the Celery broker (the `STALE` sweep, retention)
> and the cache that holds throttle counters.
>
> You can develop without it. When neither `CACHE_URL` nor `REDIS_URL` is set,
> `config.settings.development` falls back to an in-process cache, and the
> throttle classes in `common/throttling.py` fail open if the configured cache
> is unreachable - so a dead Redis degrades rate limiting instead of returning
> 500 from every endpoint. Celery itself still needs a real broker; until you
> have one, run the sweep by hand:
>
> ```bash
> python manage.py shell -c "from presence.tasks import detect_stale_presence; print(detect_stale_presence())"
> ```

---

## 2. Migrating a database that predates this change

If your database was created when the project still used PostGIS, its
`geofences_geofence` table has `center_point`/`geometry` geometry columns and
`migrate` will *not* fix it - the migrations were rewritten in place, so Django
already considers them applied. Two options:

* **Keep your data** - run
  [`scripts/migrate_from_postgis.sql`](../scripts/migrate_from_postgis.sql) once.
  It backfills the float columns from the geometry, converts every `POLYGON`
  into its bounding `RECTANGLE`, drops the geometry columns and removes the
  stale migration record. PostGIS must still be installed while that script
  runs; afterwards it is never needed again.
* **Start clean** - drop and recreate the database, then `python manage.py migrate`.

A `POLYGON` becomes its axis-aligned bounding box, so any non-rectangular fence
will cover more ground than before. The script prints every converted row at the
end so you can review and redraw them.

Verify:

```bash
python manage.py makemigrations --check --dry-run   # "No changes detected"
python manage.py migrate
curl http://localhost:8000/health/                  # reports the server version
```

---

## 3. Project setup

```bash
python -m venv .venv
. .venv/Scripts/activate          # Linux/macOS: . .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env              # edit DJANGO_SECRET_KEY and DATABASE_URL

python manage.py migrate
python manage.py seed_demo_data   # demo tenant, admin, members, 2 geofences
python manage.py createsuperuser  # optional, for /admin/
python manage.py runserver
```

* API docs: <http://localhost:8000/api/docs/>
* Django admin: <http://localhost:8000/admin/>
* Health: <http://localhost:8000/health/>

Celery, in two more terminals (only needed for automatic `STALE` detection and
retention):

```bash
celery -A config worker --loglevel=info
celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

On Windows, prefer `celery -A config worker --loglevel=info --pool=solo`; the
default prefork pool does not work there.

---

## 4. Trying it by hand

```bash
# 1. log in
curl -s -X POST http://localhost:8000/api/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@demo.test","password":"DemoPassw0rd!2026"}'
```

```bash
# 2. send a fix at the campus centre (repeat twice to check in)
curl -s -X POST http://localhost:8000/api/location/update/ \
  -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"latitude":29.5976,"longitude":79.6591,"accuracy":12,"recorded_at":"2026-08-26T12:20:15Z"}'
```

```bash
# 3. see what the backend decided
curl -s http://localhost:8000/api/presence/me/ -H "Authorization: Bearer $ACCESS"
```

Remember that `recorded_at` must be within `MAX_LOCATION_AGE_SECONDS` (one hour)
of now, or the fix is rejected as stale.

---

## 5. Tests

```bash
pytest                 # full suite
pytest -q -x           # stop at the first failure
make test-fast         # only the tests that need no database
pytest --cov           # coverage
```

Most tests need a live PostgreSQL database - they exercise the check
constraints, the advisory locking and the concurrency behaviour, none of which
SQLite reproduces. **No PostGIS extension is required.** pytest creates and
reuses `test_geofencing` (`--reuse-db` is on by default in `pyproject.toml`; add
`--create-db` after a migration change), so the role in `DATABASE_URL` needs
`CREATEDB` - and nothing more. The superuser rights the old PostGIS setup
demanded are gone.

Roughly 90 tests - the geometry primitives (`tests/test_geo_math.py`), the state
machine, the verdict function and all input validation - run with no database at
all, which is where most of the domain logic lives.

---

## 6. Code quality

```bash
ruff check .        # lint
black .             # format
mypy .              # types
python manage.py check --deploy   # production readiness checklist
python manage.py spectacular --file docs/openapi.yaml   # refresh the schema
```
