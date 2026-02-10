"""Runtime health registry for operational visibility."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from threading import RLock
from typing import Any

from flask import Flask

from webapp.services.operational_alerts import get_operational_alert_telemetry


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class RuntimeHealthRegistry:
    """Thread-safe in-memory runtime health state."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._started_at_utc = _utc_now_iso()
        self._startup_config_audit: dict[str, list[str]] = {
            "warnings": [],
            "errors": [],
        }
        self._scheduler: dict[str, Any] = {
            "enabled": False,
            "started": False,
            "warnings": [],
            "registered_jobs": [],
            "skipped_jobs": [],
        }
        self._jobs: dict[str, dict[str, Any]] = {}

    def set_startup_config_audit(self, audit: dict[str, list[str]]) -> None:
        with self._lock:
            self._startup_config_audit = {
                "warnings": list(audit.get("warnings", [])),
                "errors": list(audit.get("errors", [])),
            }

    def register_job(self, job_id: str, cron_expression: str) -> None:
        with self._lock:
            state = self._jobs.setdefault(job_id, _empty_job_state())
            state["cron_expression"] = cron_expression

    def mark_job_started(self, job_id: str) -> None:
        with self._lock:
            state = self._jobs.setdefault(job_id, _empty_job_state())
            state["last_status"] = "running"
            state["last_run_started_utc"] = _utc_now_iso()

    def mark_job_success(self, job_id: str, *, duration_ms: int | None = None) -> None:
        with self._lock:
            state = self._jobs.setdefault(job_id, _empty_job_state())
            state["last_success_utc"] = _utc_now_iso()
            state["last_failure_utc"] = None
            state["last_failure_reason"] = None
            state["last_status"] = "success"
            state["last_run_finished_utc"] = _utc_now_iso()
            state["success_count"] += 1
            state["run_count"] += 1
            if duration_ms is not None:
                state["last_duration_ms"] = duration_ms

    def mark_job_failure(
        self,
        job_id: str,
        reason: str,
        *,
        duration_ms: int | None = None,
    ) -> None:
        with self._lock:
            state = self._jobs.setdefault(job_id, _empty_job_state())
            state["last_failure_utc"] = _utc_now_iso()
            state["last_failure_reason"] = reason
            state["last_status"] = "failed"
            state["last_run_finished_utc"] = _utc_now_iso()
            state["failure_count"] += 1
            state["run_count"] += 1
            if duration_ms is not None:
                state["last_duration_ms"] = duration_ms

    def mark_job_skipped(self, job_id: str, reason: str) -> None:
        with self._lock:
            state = self._jobs.setdefault(job_id, _empty_job_state())
            state["last_status"] = "skipped"
            state["last_skip_reason"] = reason
            state["last_run_finished_utc"] = _utc_now_iso()
            state["skip_count"] += 1
            state["run_count"] += 1

    def set_scheduler_state(
        self,
        *,
        enabled: bool,
        started: bool,
        warnings: list[str] | None = None,
        registered_jobs: list[str] | None = None,
        skipped_jobs: list[dict[str, str]] | None = None,
    ) -> None:
        with self._lock:
            self._scheduler = {
                "enabled": enabled,
                "started": started,
                "warnings": list(warnings or []),
                "registered_jobs": list(registered_jobs or []),
                "skipped_jobs": list(skipped_jobs or []),
            }

    def build_report(self, app: Flask | None = None) -> dict[str, Any]:
        with self._lock:
            status, degraded_reasons = self._derive_status_locked()
            report = {
                "status": status,
                "degraded_reasons": degraded_reasons,
                "timestamp_utc": _utc_now_iso(),
                "started_at_utc": self._started_at_utc,
                "startup_config_audit": deepcopy(self._startup_config_audit),
                "scheduler": deepcopy(self._scheduler),
                "jobs": deepcopy(self._jobs),
                "queue": {},
            }

        if app is not None:
            report["queue"] = self._collect_queue_summary(app)
        report["alerting"] = get_operational_alert_telemetry()
        return report

    def _collect_queue_summary(self, app: Flask) -> dict[str, Any]:
        task_queue = app.extensions.get("task_queue")
        dead_letter_queue = app.extensions.get("dead_letter_queue")
        detected_queue_extensions = sorted(
            key for key in app.extensions.keys() if "queue" in str(key).lower()
        )

        return {
            "available": task_queue is not None or dead_letter_queue is not None,
            "task_queue_size": _safe_queue_size(task_queue),
            "dead_letter_queue_size": _safe_queue_size(dead_letter_queue),
            "detected_extensions": detected_queue_extensions,
        }

    def _derive_status_locked(self) -> tuple[str, list[str]]:
        degraded_reasons: list[str] = []

        if self._startup_config_audit.get("errors"):
            degraded_reasons.append("startup_config_errors")

        if self._scheduler.get("enabled") and not self._scheduler.get("started"):
            degraded_reasons.append("scheduler_not_started")

        if self._scheduler.get("skipped_jobs"):
            degraded_reasons.append("scheduler_skipped_jobs")

        for job_id, job_state in self._jobs.items():
            if job_state.get("last_status") == "failed":
                degraded_reasons.append(f"job_failed:{job_id}")

        if degraded_reasons:
            return "degraded", degraded_reasons
        return "healthy", []


def _safe_queue_size(queue_obj: Any) -> int | None:
    if queue_obj is None:
        return None

    size_attr = getattr(queue_obj, "size", None)
    if callable(size_attr):
        try:
            return int(size_attr())
        except Exception:
            return None

    qsize_attr = getattr(queue_obj, "qsize", None)
    if callable(qsize_attr):
        try:
            return int(qsize_attr())
        except Exception:
            return None

    try:
        return len(queue_obj)
    except Exception:
        return None


def _empty_job_state() -> dict[str, Any]:
    return {
        "cron_expression": None,
        "last_status": None,
        "last_run_started_utc": None,
        "last_run_finished_utc": None,
        "last_duration_ms": None,
        "last_success_utc": None,
        "last_failure_utc": None,
        "last_failure_reason": None,
        "last_skip_reason": None,
        "run_count": 0,
        "success_count": 0,
        "failure_count": 0,
        "skip_count": 0,
    }


runtime_health = RuntimeHealthRegistry()
