"""
cache.py — Lightweight in-process TTL cache for the Panel Portal backend.

Eliminates the repeated Supabase round-trips that are made on every page load
for data that only changes rarely (active team IDs, meet-link map, project titles).
"""

import threading
import time
from typing import Any, Callable, TypeVar

_T = TypeVar("_T")

_store: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def get_cached(key: str, ttl_seconds: float, factory: Callable[[], _T]) -> _T:
    """
    Return a cached value for *key*, calling *factory* to refresh it when
    the entry is missing or older than *ttl_seconds*.
    Thread-safe.
    """
    now = time.monotonic()
    with _lock:
        entry = _store.get(key)
        if entry is not None:
            ts, val = entry
            if now - ts < ttl_seconds:
                print(f"[CACHE HIT] key={key}")
                return val  # type: ignore[return-value]

    # Compute outside the lock so we don't block other threads
    print(f"[CACHE MISS] key={key}")
    val = factory()

    with _lock:
        _store[key] = (time.monotonic(), val)

    return val  # type: ignore[return-value]


def get_or_set(key: str, ttl_seconds: float, factory: Callable[[], _T]) -> _T:
    """Alias for get_cached — preferred public API name."""
    return get_cached(key, ttl_seconds, factory)


def peek(key: str, ttl_seconds: float) -> tuple[bool, Any]:
    """
    Check whether *key* exists in cache and is still fresh.
    Returns (hit: bool, value: Any).  Does not call factory.
    """
    now = time.monotonic()
    with _lock:
        entry = _store.get(key)
        if entry is not None:
            ts, val = entry
            if now - ts < ttl_seconds:
                return True, val
    return False, None


def set_value(key: str, value: Any) -> None:
    """Directly store a value in the cache with the current timestamp."""
    with _lock:
        _store[key] = (time.monotonic(), value)


def invalidate(key: str) -> None:
    """Remove a single key from the cache."""
    with _lock:
        _store.pop(key, None)


def invalidate_prefix(prefix: str) -> None:
    """Remove all keys that start with *prefix*."""
    with _lock:
        for k in list(_store.keys()):
            if k.startswith(prefix):
                del _store[k]


def clear_all() -> None:
    with _lock:
        _store.clear()
