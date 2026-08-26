# Geofencing Presence Backend

Django + PostgreSQL backend for a PWA based attendance/presence system. An
organization draws a tracking area on a map (a circle or a rectangle); members'
browsers report GPS fixes; **the backend decides who is present**.

There is **no PostGIS / GeoDjango / GDAL dependency**: geofences are stored as
ordinary float columns and every geographic comparison runs in Python
([`common/utils/geo.py`](common/utils/geo.py)), so a stock PostgreSQL server and
the `psycopg` wheel are the whole database story.

The interesting part of this project is not CRUD. It is the two mechanisms that
make browser GPS usable for attendance:

1. a **geofence evaluator** that treats accuracy as first-class data and returns
   `INSIDE` / `OUTSIDE` / `UNCERTAIN`, and
2. a **presence state machine** with hysteresis, debouncing and an explicit
   `STALE` state, so that one bad fix never checks anybody out and silence is
   never mistaken for departure.

---

## Contents

| Document | What it covers |
|---|---|
| [docs/GEOFENCE_ALGORITHM.md](docs/GEOFENCE_ALGORITHM.md) | Signed distance model, accuracy margin, why thresholds are what they are |
| [docs/PRESENCE_STATE_MACHINE.md](docs/PRESENCE_STATE_MACHINE.md) | States, transitions, and the reasoning behind every rule |
| [docs/API.md](docs/API.md) | Endpoint reference with request/response examples |
| [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) | Every environment variable |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Local setup, PostgreSQL install, Windows notes, testing |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production deployment |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model, authorization, anti-spoofing honesty |
| [docs/PRIVACY.md](docs/PRIVACY.md) | What is collected, who can read it, retention |
| [docs/PWA_LIMITATIONS.md](docs/PWA_LIMITATIONS.md) | What browser geolocation can and cannot do |
| [docs/openapi.yaml](docs/openapi.yaml) | Generated OpenAPI 3 schema (also at `/api/docs/`) |

---

## Quick start

```bash
docker compose up -d db redis
```

```bash
python -m venv .venv && . .venv/Scripts/activate   # Linux/macOS: . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # then edit DJANGO_SECRET_KEY and DATABASE_URL
python manage.py migrate
python manage.py seed_demo_data
python manage.py runserver
```

Open <http://localhost:8000/api/docs/> for interactive API documentation.

Sign in with the seeded super admin (`admin@demo.test` / `DemoPassw0rd!2026`):

```bash
curl -s -X POST http://localhost:8000/api/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@demo.test","password":"DemoPassw0rd!2026"}'
```

Run Celery in two more terminals (needed for `STALE` detection):

```bash
celery -A config worker --loglevel=info
```

```bash
celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

---

## Architecture

Strict one-way layering. Nothing skips a layer, and nothing calls back up.

```
URL ─► View            HTTP only: status codes, pagination, permissions
        └► Serializer  shape of the request/response
            └► Validator   business rules over the input; no database writes
                └► Service     transactions, state transitions, writes
                    └► Selector    reads and queries
                        └► Model       structure and database constraints
```

| App | Responsibility |
|---|---|
| `config` | settings (base/development/production/test), URLs, Celery app |
| `common` | envelope renderer, exception handler, pagination, permissions, throttles, tenancy mixin, advisory locks, geo/time helpers, tunables |
| `accounts` | custom `User` (email login), the single-admin role model, JWT endpoints |
| `organizations` | `Organization`, the tenancy root |
| `geofences` | `Geofence`, geometry validation, **the geofence evaluator** |
| `locations` | `LocationUpdate`, `LocationAnomaly`, ingest, anomaly detection, retention |
| `presence` | `Presence`, `PresenceEvent`, **the state machine**, stale sweep, dashboards |

### Data model

```
Organization 1──* User            (User.organization; null only for a platform-wide ADMIN)
Organization 1──* Geofence        (CIRCLE: center_lat/lon + radius | RECTANGLE: min/max lat/lon)
Organization 1──* LocationUpdate ──1 User
LocationUpdate 1──* LocationAnomaly
Organization 1──* Presence ──1 User, ──1 Geofence   UNIQUE(user, geofence, date)
Presence     1──* PresenceEvent   (append-only audit trail)
```

`Presence` rows are created lazily: a row exists only once a user has been
confidently inside that geofence on that day. A user with no row is `UNKNOWN`,
which is why "no GPS" can never be read as "left".

### Request flow of a location update

```
POST /api/location/update/
  │
  ├─ LocationUpdateRequestSerializer   types, ranges, forbidden "status" field
  ├─ validate_location_payload         clock skew, staleness, accuracy
  │
  └─ process_location_update()                       ← one transaction
       ├─ pg_advisory_xact_lock(user)                serialises this user
       ├─ find_replay()                              idempotency
       ├─ detect_anomalies()                         speed, jumps, frozen coords
       ├─ store_location_update()                    always stored, trusted or not
       ├─ evaluate_point()            ← pure Python  INSIDE / OUTSIDE / UNCERTAIN
       └─ apply_reading()             ← pure         state machine + events
```

---

## The two core mechanisms

### 1. Geofence evaluation

Every geofence collapses to one number `x` on a signed-distance axis and two
thresholds:

| type | `x` | enter when | exit when |
|---|---|---|---|
| `CIRCLE` | distance to `center_point` | `x ≤ entry_radius` | `x ≥ exit_radius` |
| `RECTANGLE` | signed distance to the box boundary (negative inside) | `x ≤ −entry_radius` | `x ≥ +exit_radius` |

Reported GPS accuracy becomes an uncertainty margin `m`:

```
INSIDE     if  x + m ≤ enter_threshold      whole accuracy circle is inside
OUTSIDE    if  x − m ≥ exit_threshold       whole accuracy circle is outside
UNCERTAIN  otherwise                        hysteresis band, or too imprecise
```

`UNCERTAIN` never changes state. That single rule is what makes a 12 m fix and
a 100 m fix at the same coordinates behave differently, and it is why the
system does not need to reject inaccurate readings outright.

The geometry is a haversine distance for a circle and a signed
distance-to-box for a rectangle, both in
[`common/utils/geo.py`](common/utils/geo.py); the policy is applied in
[`geofences/evaluation.py`](geofences/evaluation.py). See
[docs/GEOFENCE_ALGORITHM.md](docs/GEOFENCE_ALGORITHM.md).

### 2. Presence state machine

```
   UNKNOWN ──confident OUTSIDE──► OUTSIDE
      │                              │
      └──── N consecutive INSIDE ────┘
                    │
                    ▼
                 PRESENT ──── M consecutive OUTSIDE ────► GONE
                  │   ▲                                    │
   no update      │   │  trusted reading                   │
   for T seconds  │   │  (LOCATION_RESTORED)               │
                  ▼   │                                    │
                 STALE ─────────────────────────────────────
                        (a returning device can also exit
                         from STALE, or re-enter from GONE)
```

| from | trigger | to | event |
|---|---|---|---|
| `UNKNOWN` | confident outside | `OUTSIDE` | — |
| `UNKNOWN` / `OUTSIDE` / `GONE` | N consecutive `INSIDE` | `PRESENT` | `ENTERED` |
| `PRESENT` | M consecutive `OUTSIDE` | `GONE` | `EXITED` |
| `PRESENT` | no update for T seconds (Celery) | `STALE` | `STALE` |
| `STALE` | any trusted reading | `PRESENT` | `LOCATION_RESTORED` |
| `PRESENT` | attendance day ended (Celery) | `GONE` | `EXITED` (`DAY_ROLLOVER`) |

* Entering needs **2** consecutive `INSIDE` readings, leaving needs **3**
  consecutive `OUTSIDE` readings (both configurable, globally or per geofence).
  The asymmetry is deliberate: a false "present" is an annoyance, a false
  "left" destroys somebody's attendance record.
* A streak expires after `STREAK_MAX_GAP_SECONDS` — two readings an hour apart
  are not evidence of continuous presence.
* Out-of-order fixes (an offline PWA flushing its queue) are stored but never
  rewind the machine.
* `STALE` is reachable **only** from `PRESENT` and **only** from the Celery
  timeout task. No amount of silence can produce `GONE`.

See [docs/PRESENCE_STATE_MACHINE.md](docs/PRESENCE_STATE_MACHINE.md).

---

## API summary

Every response is enveloped:

```json
{"success": true,  "data": {...}}
{"success": false, "errors": {"field": ["message"]}}
```

| Method | Path | Who |
|---|---|---|
| POST | `/api/auth/login/` | anyone |
| POST | `/api/auth/refresh/` | anyone |
| GET | `/api/auth/me/` | member |
| GET | `/api/auth/users/` | admin |
| GET/POST | `/api/geofences/` | read: member, write: admin |
| GET/PATCH/DELETE | `/api/geofences/{id}/` | read: member, write: admin |
| POST | `/api/location/update/` | member |
| GET | `/api/location/status/` | member |
| GET | `/api/location/history/` | member (own data only) |
| GET | `/api/location/anomalies/` | admin |
| GET | `/api/presence/me/` | member |
| GET | `/api/presence/me/history/` | member |
| GET | `/api/presence/me/events/` | member |
| GET | `/api/admin/presence/` | admin |
| GET | `/api/admin/presence/summary/` | admin |
| GET | `/api/admin/presence/events/` | admin |
| GET | `/api/admin/presence/{user_id}/` | admin |
| GET | `/api/organizations/`, `/api/organizations/me/` | member |
| GET | `/health/` | anyone |

Full reference with examples: [docs/API.md](docs/API.md).

### The one rule for frontend authors

```jsonc
// POST /api/location/update/
{
  "latitude": 29.59791,
  "longitude": 79.65887,
  "accuracy": 12,
  "recorded_at": "2026-08-26T12:20:15Z",
  "client_event_id": "5f0f1f6e-2f2a-4f43-bd0f-1a3c5f9a0e11"  // optional, makes retries safe
}
```

Sending `{"status": "PRESENT"}` is rejected with `400`, not ignored. The
backend is the only authority on presence.

---

## Testing

```bash
pytest            # everything (needs PostgreSQL)
pytest -q tests/test_state_machine.py   # one file
make test-fast    # the ~55 tests that need no database at all
```

The suite covers authentication, tenancy isolation, geofence CRUD and
validation, circle and rectangle evaluation, the geometry primitives themselves,
entry/exit transitions, GPS jitter,
accuracy handling, staleness, delayed and out-of-order delivery, duplicate and
concurrent updates, impossible movement, permissions, event generation and the
Celery tasks.

A real PostgreSQL database is required for the majority of them - they exercise
the constraints and the concurrency behaviour, which SQLite cannot reproduce.
No PostGIS extension is needed. The geometry itself is pure Python and its tests
([`tests/test_geo_math.py`](tests/test_geo_math.py)) need no database at all.

---

## Production notes

* `config.settings.production` enables HSTS, secure cookies, SSL redirect and a
  strict `ALLOWED_HOSTS`/CORS allow-list. No secret has a default.
* Run at least one Celery worker **and** beat, otherwise nobody ever becomes
  `STALE`.
* Location history is purged after `LOCATION_HISTORY_RETENTION_DAYS` (30 by
  default); presence history is kept far longer. See
  [docs/PRIVACY.md](docs/PRIVACY.md).
* `POST /api/location/update/` is rate limited per user (60/min by default).

### Container boot

The image's `CMD` runs `migrate`, then `ensure_superuser --skip-if-unset`, then
`collectstatic`, then Gunicorn on `$PORT` (defaulting to 8000).

`ensure_superuser` creates the single super admin from
`DJANGO_SUPERUSER_EMAIL` / `DJANGO_SUPERUSER_PASSWORD` (and optional
`DJANGO_SUPERUSER_NAME`). It is idempotent, so a redeploy over an existing
database is a no-op rather than a failed deploy. **There is no
`DJANGO_SUPERUSER_USERNAME`**: this project's `User` model has no `username`
field - email is `USERNAME_FIELD` - and any such variable is ignored.

### Upgrading a database created before the PostGIS removal

`migrate` cannot detect this: the geofence migrations were rewritten in place,
so an older database already has `0001_initial` recorded and `migrate` reports
"No migrations to apply" while the table still has geometry columns. Check with:

```bash
python manage.py check_geofence_schema     # exits 1 if conversion is needed
```

and convert with [`scripts/migrate_from_postgis.sql`](scripts/migrate_from_postgis.sql).

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

---

## What this system deliberately does not claim

Browser geolocation cannot be made spoof-proof. A user with developer tools can
report any coordinates they like, and no server-side check changes that. What
this backend does instead is record plausibility signals — impossible speed,
teleporting, frozen coordinates, absurd accuracy, abnormal update rates — as
`LocationAnomaly` rows for a human to review. Only physically impossible
readings are excluded from presence decisions, and **no user is ever
automatically punished for an anomaly**. If tamper resistance matters more than
convenience, the honest answer is a native or hybrid app with platform
attestation, not a PWA. See [docs/PWA_LIMITATIONS.md](docs/PWA_LIMITATIONS.md).
