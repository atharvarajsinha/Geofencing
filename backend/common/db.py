"""Database helpers: advisory locking and small query utilities."""
from __future__ import annotations

from django.db import connection, transaction

#: 32-bit namespaces for ``pg_advisory_xact_lock``. Keep them unique per
#: serialisation domain so unrelated features never block each other.
LOCK_NAMESPACE_LOCATION_PROCESSING = 4201
LOCK_NAMESPACE_PRESENCE_STALE_SCAN = 4202

_INT32_MASK = 0x7FFFFFFF


def _to_int32(value: int | str) -> int:
    """Fold an arbitrary identifier into a positive 32-bit integer."""
    if isinstance(value, int):
        return value & _INT32_MASK
    return hash(value) & _INT32_MASK


def advisory_xact_lock(namespace: int, key: int | str) -> None:
    """Serialise a critical section across processes for the current transaction.

    Blocks until the lock is held. It is released automatically when the
    surrounding transaction ends, which is exactly the behaviour location
    processing needs: two simultaneous updates from the same device are handled
    one after the other and never interleave their presence transitions.

    Deliberately a plain function, not a context manager. There is nothing to
    do on exit - COMMIT/ROLLBACK does the releasing - and a ``@contextmanager``
    here is a trap: calling it without ``with`` builds a generator whose body
    never runs, so the lock is silently never taken.
    """
    if not connection.in_atomic_block:
        raise RuntimeError(
            "advisory_xact_lock() must be called inside an atomic block; "
            "transaction-scoped locks are released at COMMIT/ROLLBACK."
        )
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [namespace, _to_int32(key)])


def on_commit(callback) -> None:  # pragma: no cover - thin wrapper
    """Run ``callback`` once the surrounding transaction commits."""
    transaction.on_commit(callback)
