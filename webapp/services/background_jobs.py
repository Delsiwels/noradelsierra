"""Boot-safe APScheduler integration for operational background jobs."""

from __future__ import annotations

import atexit
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field

from flask import Flask

from webapp.services.runtime_health import runtime_health
from webapp.services.scheduler_config import resolve_job_schedule

logger = logging.getLogger(__name__)

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
except Exception:  # pragma: no cover - exercised in integration environments
    BackgroundScheduler = None
    CronTrigger = None


@dataclass(frozen=True)
class ManagedJob:
    """Background job registration descriptor."""

    job_id: str
    func: Callable[[], object]
    cron_env_var: str | None = None
    interval_env_var: str | None = None
    default_interval_minutes: int = 60
    fallback_minute: int = 0


@dataclass
class SchedulerBootReport:
    """Result of background scheduler boot attempt."""

    enabled: bool
    started: bool = False
    warnings: list[str] = field(default_factory=list)
    registered_jobs: list[str] = field(default_factory=list)
    skipped_jobs: list[dict[str, str]] = field(default_factory=list)


def start_background_scheduler(
    app: Flask,
    jobs: list[ManagedJob],
) -> SchedulerBootReport:
    """Register jobs with APScheduler without blocking app boot on invalid job config."""
    default_enabled = not bool(app.config.get("TESTING", False))
    enabled = _read_bool_env("ENABLE_BACKGROUND_JOBS", default=default_enabled)
    report = SchedulerBootReport(enabled=enabled)

    if not enabled:
        runtime_health.set_scheduler_state(
            enabled=False,
            started=False,
            warnings=["Background jobs disabled by ENABLE_BACKGROUND_JOBS flag."],
        )
        return report

    if BackgroundScheduler is None or CronTrigger is None:
        message = "APScheduler is unavailable; background jobs disabled."
        report.warnings.append(message)
        logger.warning(message)
        runtime_health.set_scheduler_state(
            enabled=True,
            started=False,
            warnings=report.warnings,
            registered_jobs=report.registered_jobs,
            skipped_jobs=report.skipped_jobs,
        )
        return report

    scheduler = BackgroundScheduler(timezone="UTC")

    for job in jobs:
        cron_value = _read_str_env(job.cron_env_var) if job.cron_env_var else None
        interval_value = (
            _read_str_env(job.interval_env_var) if job.interval_env_var else None
        )
        schedule = resolve_job_schedule(
            job_name=job.job_id,
            cron_value=cron_value,
            interval_value=interval_value,
            default_interval_minutes=job.default_interval_minutes,
            fallback_minute=job.fallback_minute,
        )

        if schedule.warning:
            report.warnings.append(schedule.warning)
            logger.warning(schedule.warning)

        wrapped_job = _wrap_job(job.job_id, job.func)

        try:
            trigger = CronTrigger.from_crontab(schedule.cron_expression)
            scheduler.add_job(
                wrapped_job,
                trigger=trigger,
                id=job.job_id,
                replace_existing=True,
                coalesce=True,
                misfire_grace_time=300,
            )
            runtime_health.register_job(job.job_id, schedule.cron_expression)
            report.registered_jobs.append(job.job_id)
        except (
            Exception
        ) as exc:  # pragma: no cover - behavior validated by report output
            reason = f"{type(exc).__name__}: {exc}"
            report.skipped_jobs.append({"job_id": job.job_id, "reason": reason})
            report.warnings.append(
                f"{job.job_id}: skipped due to invalid schedule/config ({reason})."
            )
            logger.warning("Skipping background job %s: %s", job.job_id, reason)

    if not report.registered_jobs:
        report.warnings.append(
            "No background jobs registered; scheduler start skipped."
        )
        runtime_health.set_scheduler_state(
            enabled=True,
            started=False,
            warnings=report.warnings,
            registered_jobs=report.registered_jobs,
            skipped_jobs=report.skipped_jobs,
        )
        return report

    try:
        scheduler.start()
        report.started = True
        app.extensions["background_scheduler"] = scheduler
        atexit.register(_shutdown_scheduler, scheduler)
    except Exception as exc:  # pragma: no cover - rare runtime branch
        reason = f"{type(exc).__name__}: {exc}"
        report.warnings.append(f"Scheduler failed to start ({reason}).")
        logger.exception("Background scheduler failed to start")

    runtime_health.set_scheduler_state(
        enabled=True,
        started=report.started,
        warnings=report.warnings,
        registered_jobs=report.registered_jobs,
        skipped_jobs=report.skipped_jobs,
    )
    return report


def _shutdown_scheduler(scheduler: BackgroundScheduler) -> None:
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        logger.debug("Background scheduler shutdown skipped/failed.", exc_info=True)


def _wrap_job(job_id: str, job_func: Callable[[], object]) -> Callable[[], None]:
    def runner() -> None:
        try:
            job_func()
            runtime_health.mark_job_success(job_id)
        except Exception as exc:
            runtime_health.mark_job_failure(job_id, str(exc))
            logger.exception("Background job '%s' failed", job_id)
            raise

    return runner


def _read_bool_env(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _read_str_env(name: str | None) -> str | None:
    if not name:
        return None
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None
