"""Boot-safe APScheduler integration for operational background jobs."""

from __future__ import annotations

import atexit
import concurrent.futures
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from flask import Flask

from webapp.services.operational_alerts import send_operational_alert
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
    max_runtime_seconds: int | None = None
    max_retries: int | None = None
    retry_backoff_seconds: float | None = None
    allow_overlap: bool = False


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
        app.extensions["runtime_scheduler_state"] = {
            "enabled": False,
            "started": False,
            "warnings": ["Background jobs disabled by ENABLE_BACKGROUND_JOBS flag."],
        }
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
        app.extensions["runtime_scheduler_state"] = {
            "enabled": True,
            "started": False,
            "warnings": report.warnings,
        }
        send_operational_alert(
            app,
            event_type="scheduler_boot",
            severity="high",
            message=message,
            details={"warnings": report.warnings},
            dedupe_key="scheduler_boot_unavailable",
        )
        return report

    scheduler = BackgroundScheduler(timezone="UTC")
    default_max_runtime_seconds = int(
        app.config.get("BACKGROUND_JOB_MAX_RUNTIME_SECONDS", 300)
    )
    default_max_retries = int(app.config.get("BACKGROUND_JOB_MAX_RETRIES", 1))
    default_retry_backoff_seconds = float(
        app.config.get("BACKGROUND_JOB_RETRY_BACKOFF_SECONDS", 2.0)
    )
    job_locks: dict[str, threading.Lock] = {}

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
            send_operational_alert(
                app,
                event_type="scheduler_boot_warning",
                severity="medium",
                message=schedule.warning,
                details={"job_id": job.job_id},
                dedupe_key=f"scheduler_boot_warning:{job.job_id}",
            )

        wrapped_job = _wrap_job(
            app=app,
            job=job,
            lock=job_locks.setdefault(job.job_id, threading.Lock()),
            max_runtime_seconds=_resolve_int(
                job.max_runtime_seconds,
                default_max_runtime_seconds,
                minimum=1,
            ),
            max_retries=_resolve_int(job.max_retries, default_max_retries, minimum=0),
            retry_backoff_seconds=_resolve_float(
                job.retry_backoff_seconds,
                default_retry_backoff_seconds,
                minimum=0.1,
            ),
        )

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
            send_operational_alert(
                app,
                event_type="scheduler_job_skipped",
                severity="high",
                message=f"Job '{job.job_id}' was skipped during scheduler boot.",
                details={"reason": reason},
                dedupe_key=f"scheduler_job_skipped:{job.job_id}",
            )

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
        app.extensions["runtime_scheduler_state"] = {
            "enabled": True,
            "started": False,
            "warnings": report.warnings,
        }
        send_operational_alert(
            app,
            event_type="scheduler_boot",
            severity="high",
            message="No jobs were registered; scheduler did not start.",
            details={"warnings": report.warnings, "skipped_jobs": report.skipped_jobs},
            dedupe_key="scheduler_boot_no_jobs",
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
        send_operational_alert(
            app,
            event_type="scheduler_boot",
            severity="high",
            message="Scheduler failed to start.",
            details={"reason": reason},
            dedupe_key="scheduler_boot_failed_to_start",
        )

    runtime_health.set_scheduler_state(
        enabled=True,
        started=report.started,
        warnings=report.warnings,
        registered_jobs=report.registered_jobs,
        skipped_jobs=report.skipped_jobs,
    )
    app.extensions["runtime_scheduler_state"] = {
        "enabled": True,
        "started": report.started,
        "warnings": report.warnings,
    }
    return report


def _shutdown_scheduler(scheduler: BackgroundScheduler) -> None:
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        logger.debug("Background scheduler shutdown skipped/failed.", exc_info=True)


def _wrap_job(
    *,
    app: Flask,
    job: ManagedJob,
    lock: threading.Lock,
    max_runtime_seconds: int,
    max_retries: int,
    retry_backoff_seconds: float,
) -> Callable[[], None]:
    def runner() -> None:
        if not job.allow_overlap:
            acquired = lock.acquire(blocking=False)
            if not acquired:
                reason = "overlap prevented (previous run still active)"
                runtime_health.mark_job_skipped(job.job_id, reason)
                logger.warning("Skipping job %s: %s", job.job_id, reason)
                send_operational_alert(
                    app,
                    event_type="scheduler_job_overlap",
                    severity="medium",
                    message=f"Job '{job.job_id}' skipped due to overlap guard.",
                    details={"reason": reason},
                    dedupe_key=f"scheduler_job_overlap:{job.job_id}",
                )
                return
        else:
            acquired = False

        runtime_health.mark_job_started(job.job_id)
        started = time.monotonic()
        try:
            _run_job_with_retries(
                app=app,
                job=job,
                max_runtime_seconds=max_runtime_seconds,
                max_retries=max_retries,
                retry_backoff_seconds=retry_backoff_seconds,
                started_monotonic=started,
            )
        finally:
            if acquired:
                lock.release()

    return runner


def _run_job_with_retries(
    *,
    app: Flask,
    job: ManagedJob,
    max_runtime_seconds: int,
    max_retries: int,
    retry_backoff_seconds: float,
    started_monotonic: float,
) -> None:
    attempt = 0
    while attempt <= max_retries:
        outcome = _run_job_once(job.func, max_runtime_seconds=max_runtime_seconds)
        if outcome["ok"]:
            duration_ms = int((time.monotonic() - started_monotonic) * 1000)
            runtime_health.mark_job_success(job.job_id, duration_ms=duration_ms)
            return

        reason = str(outcome["reason"])
        timed_out = bool(outcome["timed_out"])
        should_retry = attempt < max_retries and not timed_out
        if should_retry:
            delay_seconds = retry_backoff_seconds * (2**attempt)
            logger.warning(
                "Job %s failed on attempt %s/%s (%s). Retrying in %.1fs",
                job.job_id,
                attempt + 1,
                max_retries + 1,
                reason,
                delay_seconds,
            )
            time.sleep(delay_seconds)
            attempt += 1
            continue

        duration_ms = int((time.monotonic() - started_monotonic) * 1000)
        runtime_health.mark_job_failure(job.job_id, reason, duration_ms=duration_ms)
        logger.error("Background job '%s' failed: %s", job.job_id, reason)
        send_operational_alert(
            app,
            event_type="scheduler_job_failure",
            severity="high",
            message=f"Job '{job.job_id}' failed.",
            details={"reason": reason, "attempts": attempt + 1},
            dedupe_key=f"scheduler_job_failure:{job.job_id}:{reason.split(':', 1)[0]}",
        )
        return


def _run_job_once(
    job_func: Callable[[], object],
    *,
    max_runtime_seconds: int,
) -> dict[str, object]:
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(job_func)
    try:
        future.result(timeout=max_runtime_seconds)
        return {"ok": True, "timed_out": False, "reason": ""}
    except concurrent.futures.TimeoutError:
        future.cancel()
        return {
            "ok": False,
            "timed_out": True,
            "reason": f"timed out after {max_runtime_seconds}s",
        }
    except Exception as exc:
        return {
            "ok": False,
            "timed_out": False,
            "reason": f"{type(exc).__name__}: {exc}",
        }
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


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


def _resolve_int(value: int | None, default: int, *, minimum: int) -> int:
    candidate = value if value is not None else default
    return max(minimum, int(candidate))


def _resolve_float(value: float | None, default: float, *, minimum: float) -> float:
    candidate = value if value is not None else default
    return max(minimum, float(candidate))
