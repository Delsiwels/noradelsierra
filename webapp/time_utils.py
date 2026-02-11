"""UTC datetime helpers with stable naive UTC output for DB compatibility."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return naive UTC datetime compatible with existing DB columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def utcnow_iso() -> str:
    """Return ISO-8601 string from naive UTC datetime."""
    return utcnow().isoformat()
