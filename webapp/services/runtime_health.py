"""Runtime health registry for operational visibility."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from threading import RLock
from typing import Any

from flask import Flask


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class RuntimeHealthRegistry:
    """Thread-safe in-memory runtime health state."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._started_at_utc = _utc_now_iso()
        self._scheduler: dict[str, Any] = {
            "enabled": False,
            "started": False,
            "warnings": [],
            "registered_jobs": [],
            "skipped_jobs": [],
        }
        self._jobs: dict[str, dict[str, Any]] = {}

    def register_job(self, job_id: str, cron_expression: str) -> None:
        with self._lock:
            state = self._jobs.setdefault(
                job_id,
                {
                    "cron_expression": cron_expression,
                    "last_success_utc": None,
                    "last_failure_utc": None,
                    "last_failure_reason": None,
                },
            )
            state["cron_expression"] = cron_expression

    def mark_job_success(self, job_id: str) -> None:
        with self._lock:
            state = self._jobs.setdefault(
                job_id,
                {
                    "cron_expression": None,
                    "last_success_utc": None,
                    "last_failure_utc": None,
                    "last_failure_reason": None,
                },
            )
            state["last_success_utc"] = _utc_now_iso()
            state["last_failure_utc"] = None
            state["last_failure_reason"] = None

    def mark_job_failure(self, job_id: str, reason: str) -> None:
        with self._lock:
            state = self._jobs.setdefault(
                job_id,
                {
                    "cron_expression": None,
                    "last_success_utc": None,
                    "last_failure_utc": None,
                    "last_failure_reason": None,
                },
            )
            state["last_failure_utc"] = _utc_now_iso()
            state["last_failure_reason"] = reason

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
            report = {
                "status": "healthy",
                "timestamp_utc": _utc_now_iso(),
                "started_at_utc": self._started_at_utc,
                "scheduler": deepcopy(self._scheduler),
                "jobs": deepcopy(self._jobs),
                "queue": {},
            }

        if app is not None:
            report["queue"] = self._collect_queue_summary(app)
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


runtime_health = RuntimeHealthRegistry()
