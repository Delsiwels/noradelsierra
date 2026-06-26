"""UTC datetime helpers with stable naive UTC output for DB compatibility."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return naive UTC datetime compatible with existing DB columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def utcnow_iso() -> str:
    """Return ISO-8601 string from naive UTC datetime."""
    return utcnow().isoformat()


def parse_xero_date(date_value: str | None) -> str | None:
    """Parse Xero ``/Date(timestamp)/`` format to a ``YYYY-MM-DD`` string.

    Non-Xero values are returned as-is (stringified); ``None``/empty inputs and
    unparseable timestamps return ``None``.
    """
    if not date_value:
        return None

    if "/Date(" in str(date_value):
        try:
            ts = int(
                str(date_value).split("(")[1].split("+")[0].split("-")[0].split(")")[0]
            )
            dt = datetime.fromtimestamp(ts / 1000)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, IndexError):
            return None

    return str(date_value)
