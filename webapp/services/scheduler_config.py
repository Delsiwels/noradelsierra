"""Schedule parsing and safety guards for background jobs."""

from __future__ import annotations

import re
from dataclasses import dataclass

MINUTE_MIN = 0
MINUTE_MAX = 59

_STEP_PATTERN = re.compile(r"^\*/(\d+)$")
_SINGLE_PATTERN = re.compile(r"^\d+$")
_LIST_PATTERN = re.compile(r"^\d+(,\d+)+$")
_RANGE_PATTERN = re.compile(r"^(\d+)-(\d+)(?:/(\d+))?$")


@dataclass(frozen=True)
class ScheduleResolution:
    """Resolved cron schedule and optional warning."""

    cron_expression: str
    warning: str | None = None


def resolve_job_schedule(
    *,
    job_name: str,
    cron_value: str | None,
    interval_value: str | None,
    default_interval_minutes: int = 60,
    fallback_minute: int = 0,
) -> ScheduleResolution:
    """
    Resolve a safe 5-part cron expression for a background job.

    Priority order:
    1. Explicit cron value (`cron_value`)
    2. Interval value in minutes (`interval_value`)
    3. Default interval
    """
    if cron_value and cron_value.strip():
        return _resolve_explicit_cron(
            job_name=job_name,
            raw_value=cron_value.strip(),
            fallback_minute=fallback_minute,
        )

    if interval_value and interval_value.strip():
        return _resolve_interval_minutes(
            job_name=job_name,
            raw_value=interval_value.strip(),
            fallback_minute=fallback_minute,
            warn_on_clamp=True,
        )

    return _resolve_interval_minutes(
        job_name=job_name,
        raw_value=str(default_interval_minutes),
        fallback_minute=fallback_minute,
        warn_on_clamp=False,
    )


def _resolve_explicit_cron(
    *,
    job_name: str,
    raw_value: str,
    fallback_minute: int,
) -> ScheduleResolution:
    parts = raw_value.split()

    if len(parts) == 5:
        minute_token, warning = _sanitize_minute_token(
            minute_expr=parts[0],
            job_name=job_name,
            fallback_minute=fallback_minute,
        )
        parts[0] = minute_token
        return ScheduleResolution(cron_expression=" ".join(parts), warning=warning)

    minute_token, warning = _sanitize_minute_token(
        minute_expr=raw_value,
        job_name=job_name,
        fallback_minute=fallback_minute,
    )
    return ScheduleResolution(
        cron_expression=f"{minute_token} * * * *",
        warning=warning,
    )


def _resolve_interval_minutes(
    *,
    job_name: str,
    raw_value: str,
    fallback_minute: int,
    warn_on_clamp: bool,
) -> ScheduleResolution:
    fallback_cron = f"{fallback_minute} * * * *"

    try:
        interval = int(raw_value)
    except ValueError:
        return ScheduleResolution(
            cron_expression=fallback_cron,
            warning=(
                f"{job_name}: interval value '{raw_value}' is invalid; "
                f"falling back to '{fallback_cron}'."
            ),
        )

    if interval <= 0:
        return ScheduleResolution(
            cron_expression=fallback_cron,
            warning=(
                f"{job_name}: interval '{interval}' must be >= 1 minute; "
                f"falling back to '{fallback_cron}'."
            ),
        )

    if interval >= 60:
        warning = None
        if warn_on_clamp:
            warning = (
                f"{job_name}: interval '{interval}' would create minute expression "
                f"'*/{interval}' (invalid for minute range 0-59); "
                f"falling back to '{fallback_cron}'."
            )
        return ScheduleResolution(cron_expression=fallback_cron, warning=warning)

    return ScheduleResolution(cron_expression=f"*/{interval} * * * *")


def _sanitize_minute_token(
    *,
    minute_expr: str,
    job_name: str,
    fallback_minute: int,
) -> tuple[str, str | None]:
    minute_expr = minute_expr.strip()
    fallback_token = str(fallback_minute)

    if minute_expr == "*":
        return minute_expr, None

    step_match = _STEP_PATTERN.match(minute_expr)
    if step_match:
        step = int(step_match.group(1))
        if 1 <= step <= MINUTE_MAX:
            return minute_expr, None
        return _fallback_minute_token(
            job_name=job_name,
            original=minute_expr,
            fallback_token=fallback_token,
        )

    if _SINGLE_PATTERN.match(minute_expr):
        value = int(minute_expr)
        if MINUTE_MIN <= value <= MINUTE_MAX:
            return minute_expr, None
        return _fallback_minute_token(
            job_name=job_name,
            original=minute_expr,
            fallback_token=fallback_token,
        )

    if _LIST_PATTERN.match(minute_expr):
        values = [int(v) for v in minute_expr.split(",")]
        if all(MINUTE_MIN <= v <= MINUTE_MAX for v in values):
            return minute_expr, None
        return _fallback_minute_token(
            job_name=job_name,
            original=minute_expr,
            fallback_token=fallback_token,
        )

    range_match = _RANGE_PATTERN.match(minute_expr)
    if range_match:
        start = int(range_match.group(1))
        end = int(range_match.group(2))
        step_raw = range_match.group(3)
        is_range_valid = (
            MINUTE_MIN <= start <= MINUTE_MAX
            and MINUTE_MIN <= end <= MINUTE_MAX
            and start <= end
        )
        if not is_range_valid:
            return _fallback_minute_token(
                job_name=job_name,
                original=minute_expr,
                fallback_token=fallback_token,
            )
        if step_raw is None:
            return minute_expr, None
        step = int(step_raw)
        if 1 <= step <= MINUTE_MAX:
            return minute_expr, None
        return _fallback_minute_token(
            job_name=job_name,
            original=minute_expr,
            fallback_token=fallback_token,
        )

    return _fallback_minute_token(
        job_name=job_name,
        original=minute_expr,
        fallback_token=fallback_token,
    )


def _fallback_minute_token(
    *,
    job_name: str,
    original: str,
    fallback_token: str,
) -> tuple[str, str]:
    warning = (
        f"{job_name}: minute expression '{original}' is invalid; "
        f"using minute '{fallback_token}' instead."
    )
    return fallback_token, warning
