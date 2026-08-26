# Presence state machine

Implementation: [`presence/services/state_machine.py`](../presence/services/state_machine.py)
(pure functions), driven by
[`presence/services/processing.py`](../presence/services/processing.py) and
[`presence/services/staleness.py`](../presence/services/staleness.py).

The whole module is deliberately free of the ORM, the clock and settings: every
input is passed in. That is what makes the rules below testable in
milliseconds and readable in one screen.

---

## States

| Status | Meaning | Reachable from |
|---|---|---|
| `UNKNOWN` | Nothing usable has been observed yet today | initial |
| `OUTSIDE` | Confidently outside the area | `UNKNOWN` |
| `PRESENT` | Confidently inside; the user is checked in | `UNKNOWN`, `OUTSIDE`, `GONE`, `STALE` |
| `GONE` | Was present, then confidently left | `PRESENT` |
| `STALE` | Was present, then updates stopped arriving | `PRESENT` only |

The distinction that matters most:

> **`GONE` means we watched somebody leave. `STALE` means we stopped hearing
> from their device.**

A locked phone, a dead battery, a tunnel and a closed browser tab all look
identical to the server, and none of them is evidence of departure. Systems
that collapse these into "absent" produce attendance records that punish people
for their battery life.

---

## Transitions

| From | Trigger | To | Event | Side effects |
|---|---|---|---|---|
| `UNKNOWN` | one confident `OUTSIDE` reading | `OUTSIDE` | *(none)* | — |
| `UNKNOWN`/`OUTSIDE`/`GONE` | N consecutive `INSIDE` | `PRESENT` | `ENTERED` | `check_in_at` set if this is the first check-in of the day |
| `PRESENT` | M consecutive `OUTSIDE` | `GONE` | `EXITED` | `check_out_at` updated |
| `PRESENT` | no update for T seconds (Celery) | `STALE` | `STALE` | `stale_since` set; **`check_out_at` untouched** |
| `STALE` | any trusted reading | `PRESENT` | `LOCATION_RESTORED` | `stale_since` cleared |
| `PRESENT` | attendance day ended (Celery) | `GONE` | `EXITED` (reason `DAY_ROLLOVER`) | `check_out_at` = `last_seen_at` |
| any | `UNCERTAIN` reading | *unchanged* | — | counters untouched |
| any | out-of-order reading | *unchanged* | — | fix still stored as history |
| any | untrusted reading (HIGH anomaly) | *unchanged* | — | fix stored and flagged |

Defaults: N = 2 (`REQUIRED_INSIDE_READINGS`), M = 3
(`REQUIRED_OUTSIDE_READINGS`), T = 300 s (`STALE_AFTER_SECONDS`). All three are
configurable globally and per geofence.

---

## Design decisions and their reasons

### Hysteresis: two boundaries, not one

A single boundary makes a user standing at the edge flip between states on
every reading, producing a shower of `ENTERED`/`EXITED` events. Two boundaries
create a dead band: the fix must reach `entry_radius` to enter and pass
`exit_radius` to leave, so ordinary GPS wobble in between changes nothing.

With a 150 m campus circle the defaults give an entry radius of 150 m and an
exit radius of 190 m. A user sitting 170 m from the centre stays in whatever
state they were in.

### Debouncing: consecutive readings

Hysteresis handles *position* noise; consecutive-reading counters handle
*outlier* noise — the single fix that lands 400 m away because the phone
switched from GPS to Wi-Fi positioning. One such reading advances the counter to
1 and changes nothing; the next good reading resets it to 0.

### Asymmetric thresholds (2 in, 3 out)

The costs are not symmetric:

* a false `PRESENT` marks somebody present a minute early — an annoyance;
* a false `GONE` closes their attendance and needs a human to fix — a real
  problem for the person affected.

So leaving demands more evidence than entering. Raise `REQUIRED_OUTSIDE_READINGS`
further where the boundary is noisy (dense buildings, urban canyons); lower
`REQUIRED_INSIDE_READINGS` to 1 only where check-in latency matters more than
accuracy.

The cost of the defaults is latency: at a 60 s ping interval, check-in takes up
to ~2 minutes and check-out up to ~3. Deployments that ping every 15 s get the
same robustness in a quarter of the time.

### `UNCERTAIN` readings are inert

They neither advance nor reset a streak. Advancing would defeat the hysteresis
band; resetting would let a user hovering at the boundary permanently prevent
their own check-in. Being inert means the state simply holds, which is the
honest response to an inconclusive observation.

### Streaks expire

Two `INSIDE` readings three hours apart are not evidence of continuous
presence. If the gap between consecutive readings exceeds
`STREAK_MAX_GAP_SECONDS` (300 s) both counters reset. Without this rule, a
device that reports once an hour would accumulate a "streak" that means nothing.

### Out-of-order deliveries never rewind the machine

A PWA that was offline flushes its queue when it reconnects, and those requests
can arrive in any order. Applying a fix older than the last one already applied
would move presence backwards in time. Such readings are stored — they are
legitimate history — and skipped for state purposes with
`skip_reason = "OUT_OF_ORDER"`, which the API reports back to the client.

### `STALE` can only come from the timeout task

No reading produces `STALE`, and the task only ever looks at `PRESENT` rows.
This is a structural guarantee rather than a convention: there is no code path
from "no data" to `GONE`. The `STALE` event records `last_seen_at` and the
timeout that fired, so a dashboard can show *"present at 11:58, silent since"*
instead of inventing a departure.

When updates resume, the first trusted reading emits `LOCATION_RESTORED` and
restores `PRESENT` — the user was present before the silence, and a single fix
proves the device is back, not that anything changed. Normal rules then apply:
if they have actually left, the next M `OUTSIDE` readings check them out.

### One row per user, geofence and day

`UNIQUE(user, geofence, date)` makes "two check-ins for the same day"
unrepresentable rather than merely unlikely. The date is the calendar day in the
**organization's** timezone, because attendance is a local-calendar concept.

Rows are created lazily, only when a user is first confidently inside. A member
who never comes near the area has no row, and the dashboard counts them as
`UNKNOWN`. A day that ends while somebody is still `PRESENT` is closed by the
hourly rollover task with an `EXITED` event explicitly tagged `DAY_ROLLOVER`,
so reports never mistake bookkeeping for an observed departure.

### Events are transitions, never readings

`PresenceEvent` rows are written only when the status actually changes. Two
hundred `INSIDE` readings in a day produce exactly one `ENTERED`. A unique
constraint on `(presence, event_type, timestamp)` is the last line of defence
against a duplicate slipping through a retry.

---

## Concurrency

Two updates from the same device can arrive simultaneously — the PWA retried
while the first request was still in flight, or two tabs are open.
`process_location_update` therefore runs the whole pipeline inside one
transaction that starts with

```sql
SELECT pg_advisory_xact_lock(4201, <user_id>);
```

Everything for that user is serialised until the transaction commits, and the
lock is released automatically on commit or rollback. Within it, presence rows
are additionally selected `FOR UPDATE`.

Consequences, all of which are covered by tests:

* no duplicate check-in or check-out,
* no two `Presence` rows for the same day,
* no contradictory ordering of transitions,
* a retry with the same `client_event_id` returns the original result with
  `duplicate: true` and HTTP 200 instead of creating a second fix.

---

## Reading the state from the API

`GET /api/presence/me/` returns one row per geofence plus an
`effective_status`, which is the highest-priority state across the user's rows:

```
PRESENT > STALE > GONE > OUTSIDE > UNKNOWN
```

"Present somewhere" beats "unknown everywhere", and a user with no rows at all
is `UNKNOWN`.

Each row also exposes `consecutive_inside` / `consecutive_outside` against
`required_inside_readings` / `required_outside_readings`, so a client can show
*"checking in… 1 of 2"* rather than appearing frozen while the machine
accumulates evidence.
