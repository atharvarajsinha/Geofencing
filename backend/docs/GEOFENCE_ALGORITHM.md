# Geofence algorithm

How the backend decides whether a GPS fix is inside a tracking area, and why it
is allowed to answer "I don't know".

Implementation: [`geofences/evaluation.py`](../geofences/evaluation.py),
[`geofences/models.py`](../geofences/models.py),
[`common/utils/geo.py`](../common/utils/geo.py).

> **No PostGIS.** Both shapes are stored as plain float columns and every
> distance is computed in Python, so the project needs no PostGIS extension and
> no native GEOS/GDAL/PROJ libraries - only a stock PostgreSQL server.

---

## 1. One axis for both shapes

A circle and a rectangle look like different problems. They are not, once the
question is phrased as *how far is this fix from the boundary, and on which
side*.

Define a signed distance `x`:

| type | `x` | enter threshold | exit threshold |
|---|---|---|---|
| `CIRCLE` | great-circle distance to (`center_latitude`, `center_longitude`) | `entry_radius` | `exit_radius` |
| `RECTANGLE` | distance to the box boundary, **negative inside** | `−entry_radius` (inset) | `+exit_radius` (outset) |

For a circle, `entry_radius`/`exit_radius` are radii. For a rectangle they are
buffers: how far *inside* the fix must be to count as entered, and how far
*outside* it must be to count as exited. Either way the constraint
`exit_radius > entry_radius` holds, and the gap between them is the hysteresis
band.

The state machine therefore never needs to know which shape it is dealing with.

### The maths

```python
# circle - common.utils.geo.haversine_distance_m
x = haversine_distance_m(lat, lon, center_latitude, center_longitude)

# rectangle - common.utils.geo.signed_distance_to_bbox_m, negative inside
dy = max((min_latitude - lat) * M_PER_DEG_LAT, (lat - max_latitude) * M_PER_DEG_LAT)
dx = max((min_longitude - lon) * scale, (lon - max_longitude) * scale)
x  = hypot(dx, dy) if dx > 0 and dy > 0 else max(dx, dy)
```

`scale` is metres per degree of longitude at the in-box latitude nearest the
point. Taking the *nearest in-box* latitude rather than the point's own matters:
for a point far north of an equatorial box, the point's own cosine would
understate the east/west distance and could report an outside fix as inside.

Reading a geofence is now an ordinary indexed `SELECT` with no geometry
functions, and the arithmetic runs in the application, so a location update
still costs a single round trip regardless of how many areas exist.

**Accuracy of the spherical model:** the sphere is accurate to roughly 0.3 % —
about 0.5 m over 150 m — an order of magnitude below the accuracy of any phone
GPS fix. For rectangles there is one further approximation: `cos(latitude)` is
treated as constant across the box, which is a fraction of a percent for any
realistic site.

**Why axis-aligned rectangles and not arbitrary rectangles:** a box is the largest
shape family whose exact signed distance is a few lines of arithmetic. Arbitrary
rectangles need a point-in-rectangle test and per-segment distances - implementable
in pure Python, but not needed for the sites this system tracks. A geofence that
would span the 180th meridian is rejected at validation time, which keeps every
comparison a single subtraction.

---

## 2. Accuracy is data, not noise

`navigator.geolocation` reports `coords.accuracy`: the radius, in metres, of a
68 % confidence circle around the reported position. Ignoring it is the single
most common mistake in geofencing code — it treats a 5 m fix and a 500 m fix as
equally authoritative.

The evaluator converts it into an uncertainty margin:

```python
m = min(accuracy, ACCURACY_MARGIN_CAP_M) * ACCURACY_MARGIN_FACTOR
```

and then answers conservatively:

```
INSIDE     if  x + m ≤ enter_threshold
OUTSIDE    if  x − m ≥ exit_threshold
UNCERTAIN  otherwise
```

`INSIDE` means *the entire accuracy circle lies within the entry boundary*.
`OUTSIDE` means *the entire accuracy circle lies beyond the exit boundary*.
Anything else is honestly reported as unknown.

### Worked examples (entry 80 m, exit 120 m)

| distance | accuracy | margin | verdict | why |
|---:|---:|---:|---|---|
| 60 m | 10 m | 10 | `INSIDE` | 70 ≤ 80 |
| 60 m | 100 m | 100 | `UNCERTAIN` | 160 > 80, and 60 − 100 is nowhere near 120 |
| 75 m | 10 m | 10 | `UNCERTAIN` | 85 > 80 — a few metres short of provable |
| 200 m | 10 m | 10 | `OUTSIDE` | 190 ≥ 120 |
| 200 m | 150 m | 150 | `UNCERTAIN` | 50 < 120 — the fix could be inside |
| 5 m | 2000 m | 150 (capped) | `UNCERTAIN` | an IP-derived "fix" proves nothing |

The cap exists because browsers falling back to IP geolocation report accuracy
in kilometres. Without it, one such reading would make every subsequent verdict
uncertain until the device recovered, and the cap keeps the margin bounded at a
value that is still far larger than any real GPS error.

### Tuning

* `ACCURACY_MARGIN_FACTOR = 1.0` (default) is strict: it requires proof.
* `0.5` uses half the accuracy radius — pragmatic when a deployment's phones
  report pessimistic accuracy and users complain about slow check-ins.
* `0.0` disables accuracy handling entirely. Don't.

Widening the geofence instead of lowering the factor is the wrong fix: it also
moves the exit boundary, which makes departures harder to detect.

---

## 3. Confidence versus verdict

Two separate ideas, deliberately not merged:

* **verdict** — `INSIDE` / `OUTSIDE` / `UNCERTAIN`, drives the state machine;
* **confidence** — `HIGH` when `accuracy ≤ MAX_ACCEPTABLE_ACCURACY_M` (50 m by
  default), otherwise `LOW`. Stored on every `LocationUpdate` and reported to
  admins.

A `LOW` confidence fix is *not* discarded. If the margin still puts it entirely
inside the entry boundary, it is `INSIDE` and it counts. The margin already
encodes the risk; discarding readings would only make the system blind. What
`LOW` confidence does do is raise a `POOR_ACCURACY` anomaly so an administrator
can see that a particular device is reporting badly.

Readings worse than `HARD_REJECT_ACCURACY_M` (1000 m) are rejected at the API
boundary: at that point the payload carries no information about a 150 m
geofence at all.

---

## 4. Which geofences are evaluated

For each update the evaluator considers:

* every **active** geofence of the user's organization, plus
* every geofence for which the user already has a presence row today — even if
  it was deactivated in the meantime, because otherwise somebody could stay
  `PRESENT` forever in a retired area.

Never any other organization's geofences: two tenants may legitimately cover
the same physical place, and each must only ever see its own.

Overlapping areas are supported and evaluated independently — a user can be
`PRESENT` in "Campus" and `OUTSIDE` "Library" at the same instant. The number
of geofences evaluated per update is bounded by
`MAX_GEOFENCES_EVALUATED_PER_UPDATE`.

---

## 5. Geometry validation

Client input is coordinates, never geometry the backend trusts. Before anything
is stored, [`geofences/validators.py`](../geofences/validators.py) enforces:

* latitude ∈ [−90, 90], longitude ∈ [−180, 180], per vertex;
* at least 3 distinct vertices; the ring is closed automatically;
* edge ordering — `max_latitude` must exceed `min_latitude` and `max_longitude`
  must exceed `min_longitude`. A swapped pair is *rejected, never silently
  corrected*: it almost always means latitude and longitude were transposed, and
  quietly reordering would place the fence somewhere the admin never drew;
* a minimum edge length, so the hysteresis band cannot swallow the whole shape;
* no interior rings (holes are not supported);
* an area ceiling, so a mistyped coordinate cannot become a
  denial-of-service vector;
* radius within `[MIN_RADIUS_M, MAX_RADIUS_M]`;
* `exit_radius > entry_radius`, enforced again by a database `CheckConstraint`.

Axis order deserves a warning: mapping libraries and GeoJSON use
`[longitude, latitude]`, while the Geolocation API reports
`{latitude, longitude}`. The geofence API takes GeoJSON order for
`coordinates` and named fields for circles, and every conversion in the
codebase goes through `common.utils.geo.to_point` so the order is decided
exactly once.

---

## 6. Configuration reference

| Setting | Default | Effect |
|---|---:|---|
| `MAX_ACCEPTABLE_ACCURACY_M` | 50 | Boundary between `HIGH` and `LOW` confidence |
| `HARD_REJECT_ACCURACY_M` | 1000 | Payload rejected above this |
| `ACCURACY_MARGIN_FACTOR` | 1.0 | Fraction of accuracy used as margin |
| `ACCURACY_MARGIN_CAP_M` | 150 | Upper bound on the margin |
| `DEFAULT_ENTRY_BUFFER_M` | 0 | Default inset when the admin gives no `entry_radius` |
| `DEFAULT_EXIT_BUFFER_M` | 40 | Default hysteresis band width |
| `MIN_RADIUS_M` / `MAX_RADIUS_M` | 10 / 50 000 | Circle radius bounds |
| `MAX_GEOFENCE_AREA_KM2` | 500 | Size ceiling for either shape |
| `MAX_GEOFENCES_EVALUATED_PER_UPDATE` | 50 | Work bound per update |

Per-geofence overrides exist for the debouncing thresholds
(`required_inside_readings`, `required_outside_readings`, `stale_after_seconds`);
`GET /api/geofences/{id}/` returns the resolved values under
`effective_thresholds` so nobody has to guess what is actually in force.
