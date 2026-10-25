"""SQLite returns naive datetimes; normalize to UTC for comparisons."""

from datetime import datetime, timezone


def utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
