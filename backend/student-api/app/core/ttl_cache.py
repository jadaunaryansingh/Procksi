"""A small bounded TTL cache.

Dependency-free so it can be unit tested without credentials or a database.

Replaces the plain-dict caches that grew without limit: entries were only ever
evicted when the *same key* was read again after expiry, so any key that was
never revisited — a rotated JWT, a one-off student id — leaked for the lifetime
of the process. This sweeps expired entries on write and enforces a hard cap, so
memory is bounded by `max_entries` regardless of key churn.

Not thread-safe by design: each API worker runs a single event loop and all
access happens from coroutines, so operations are never interleaved mid-call.
Guard it externally if that ever changes.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Callable, Optional

_MISSING = object()


class TTLCache:
    """Maps key -> value for `ttl` seconds, holding at most `max_entries`."""

    def __init__(
        self,
        ttl: float,
        max_entries: int,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        if ttl < 0:
            raise ValueError("ttl must not be negative")
        self._ttl = ttl
        self._max_entries = max_entries
        self._clock = clock or time.monotonic
        # Insertion-ordered, so the oldest entry is the first one.
        # Each record is (stored_at, expires_after, value).
        self._entries: "OrderedDict[Any, tuple]" = OrderedDict()

    def __len__(self) -> int:
        return len(self._entries)

    @staticmethod
    def _expired(stored_at: float, expires_after: float, now: float) -> bool:
        return (now - stored_at) >= expires_after

    def _sweep(self, now: float) -> None:
        """Drop every expired entry. This is what reclaims keys nothing reads again."""
        expired = [
            k for k, (at, ttl, _) in self._entries.items() if self._expired(at, ttl, now)
        ]
        for key in expired:
            del self._entries[key]

    def get(self, key: Any, default: Any = None) -> Any:
        """Return the cached value, or `default` if absent or expired.

        Use a sentinel as `default` to tell a cached falsy value apart from a miss.
        """
        record = self._entries.get(key, _MISSING)
        if record is _MISSING:
            return default
        stored_at, expires_after, value = record
        if self._expired(stored_at, expires_after, self._clock()):
            del self._entries[key]
            return default
        return value

    def set(self, key: Any, value: Any, ttl: Optional[float] = None) -> None:
        """Store `value`. `ttl` overrides the cache default for this entry only."""
        now = self._clock()
        self._sweep(now)

        # Re-setting an existing key restarts its TTL and its eviction position.
        if key in self._entries:
            del self._entries[key]

        self._entries[key] = (now, self._ttl if ttl is None else ttl, value)

        # Still over the cap after sweeping: drop oldest-first.
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def pop(self, key: Any, default: Any = None) -> Any:
        """Remove `key` and return its value (ignoring expiry), else `default`."""
        record = self._entries.pop(key, _MISSING)
        if record is _MISSING:
            return default
        return record[2]

    def clear(self) -> None:
        self._entries.clear()
