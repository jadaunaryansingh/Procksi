"""
cache.py — Lightweight in-process TTL cache for the Mentor Portal backend.

Eliminates repeated database queries and Supabase round-trips made on every request
for mentor data, allocations, team validation maps, and dashboards.
"""

import threading
import time
from typing import Any, Callable, TypeVar

_T = TypeVar("_T")

_store: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def get_cached(key: str, ttl_seconds: float, factory: Callable[[], _T]) -> _T:
    """
    Return a cached value for `key`, calling `factory` to compute and refresh it
    when the entry is missing or older than `ttl_seconds`.
    Thread-safe.
    """
    now = time.monotonic()
    with _lock:
        entry = _store.get(key)
        if entry is not None:
            ts, val = entry
            if now - ts < ttl_seconds:
                print(f"[CACHE HIT] key={key}")
                return val

    # Compute outside the lock so we don't block other threads
    print(f"[CACHE MISS] key={key}")
    val = factory()

    with _lock:
        _store[key] = (time.monotonic(), val)

    return val


def get_or_set(key: str, ttl_seconds: float, factory: Callable[[], _T]) -> _T:
    """Alias for get_cached."""
    return get_cached(key, ttl_seconds, factory)


def peek(key: str, ttl_seconds: float) -> tuple[bool, Any]:
    """Check whether key exists in cache and is still fresh. Returns (hit, value)."""
    now = time.monotonic()
    with _lock:
        entry = _store.get(key)
        if entry is not None:
            ts, val = entry
            if now - ts < ttl_seconds:
                return True, val
    return False, None


def set_value(key: str, value: Any) -> None:
    """Directly store a value in the cache with current timestamp."""
    with _lock:
        _store[key] = (time.monotonic(), value)


def invalidate(key: str) -> None:
    """Remove a single key from the cache."""
    with _lock:
        _store.pop(key, None)


def invalidate_prefix(prefix: str) -> None:
    """Remove all keys starting with `prefix`."""
    with _lock:
        keys_to_del = [k for k in _store.keys() if k.startswith(prefix)]
        for k in keys_to_del:
            del _store[k]


def clear_all() -> None:
    """Clear all entries from the cache."""
    with _lock:
        _store.clear()
