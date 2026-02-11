"""CSV parsing helpers for Ask Fin journal review uploads."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB
MAX_ROWS = 2000

_COLUMN_ALIASES = {
    "date": "date",
    "account": "account",
    "description": "description",
    "debit": "debit",
    "dr": "debit",
    "credit": "credit",
    "cr": "credit",
    "gst code": "gst_code",
    "gst_code": "gst_code",
}

JournalEntry = dict[str, str | float | int]


@dataclass(slots=True)
class JournalParseResult:
    """Normalized journal parsing result."""

    entries: list[JournalEntry] = field(default_factory=list)
    row_count: int = 0
    columns: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def _normalize_column_name(name: str) -> str:
    lowered = (name or "").strip().lower()
    if lowered in _COLUMN_ALIASES:
        return _COLUMN_ALIASES[lowered]
    return lowered.replace(" ", "_")


def _parse_amount(value: object) -> float:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _entry_amount(entry: JournalEntry, key: str) -> float:
    value = entry.get(key, 0.0)
    if isinstance(value, int | float):
        return float(value)
    return _parse_amount(value)


def parse_journal_csv(payload: str | bytes) -> JournalParseResult:
    """Parse journal CSV text/bytes into normalized rows."""
    result = JournalParseResult()

    if isinstance(payload, bytes):
        if len(payload) > MAX_FILE_SIZE:
            result.error = (
                f"Uploaded file is too large. Maximum size is {MAX_FILE_SIZE} bytes."
            )
            return result
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = payload.decode("utf-8-sig", errors="replace")
    else:
        text = payload
        if len(text.encode("utf-8")) > MAX_FILE_SIZE:
            result.error = (
                f"Uploaded file is too large. Maximum size is {MAX_FILE_SIZE} bytes."
            )
            return result

    if not text or not text.strip():
        result.error = "Uploaded CSV is empty."
        return result

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        result.error = "CSV header row is missing."
        return result

    normalized_columns = {_normalize_column_name(name) for name in reader.fieldnames}
    result.columns = normalized_columns

    required_columns = {"date", "account", "debit", "credit"}
    missing = required_columns - normalized_columns
    if missing:
        pretty_names = {
            "date": "Date",
            "account": "Account",
            "debit": "Debit/Dr",
            "credit": "Credit/Cr",
        }
        missing_text = ", ".join(pretty_names[item] for item in sorted(missing))
        result.error = f"Missing required columns: {missing_text}."
        return result

    field_map = {name: _normalize_column_name(name) for name in reader.fieldnames}

    for idx, row in enumerate(reader, start=1):
        if len(result.entries) >= MAX_ROWS:
            result.warnings.append(
                f"Input exceeded {MAX_ROWS} rows and was truncated for review safety."
            )
            break

        normalized_row: JournalEntry = {}
        for source_name, value in row.items():
            target_name = field_map.get(source_name, source_name)
            normalized_row[target_name] = (value or "").strip()

        normalized_row["debit"] = _parse_amount(normalized_row.get("debit"))
        normalized_row["credit"] = _parse_amount(normalized_row.get("credit"))
        normalized_row["_row_number"] = idx
        result.entries.append(normalized_row)

    if not result.entries:
        result.error = "No data rows were found in the uploaded CSV."
        return result

    result.row_count = len(result.entries)
    return result


def format_entries_for_review(parsed: JournalParseResult) -> str:
    """Create a compact plain-text summary used by the Ask Fin reviewer."""
    if parsed.error:
        return f"Unable to review journal entries: {parsed.error}"

    total_debits = sum(_entry_amount(entry, "debit") for entry in parsed.entries)
    total_credits = sum(_entry_amount(entry, "credit") for entry in parsed.entries)
    difference = round(total_debits - total_credits, 2)

    lines = [
        f"{parsed.row_count} journal entries ready for review.",
        "Columns: " + ", ".join(sorted(parsed.columns)),
        "",
        "Preview:",
    ]

    for entry in parsed.entries[:10]:
        lines.append(
            " - Row {row}: {date} | {account} | Debit {debit:.2f} | Credit {credit:.2f}".format(
                row=entry.get("_row_number", ""),
                date=entry.get("date", ""),
                account=entry.get("account", ""),
                debit=_entry_amount(entry, "debit"),
                credit=_entry_amount(entry, "credit"),
            )
        )

    lines.append("")
    lines.append(f"Total Debits: {total_debits:.2f}")
    lines.append(f"Total Credits: {total_credits:.2f}")

    if abs(difference) > 0.01:
        lines.append(
            f"WARNING: Journal batch is not balanced (difference {difference:.2f})."
        )
    else:
        lines.append("Journal batch is balanced.")

    if parsed.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f" - {warning}" for warning in parsed.warnings)

    return "\n".join(lines)
