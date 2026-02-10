"""Tests for background job guardrail behavior."""

import time

from webapp.services.background_jobs import _run_job_once


def test_run_job_once_times_out():
    def slow_job():
        time.sleep(1.2)

    result = _run_job_once(slow_job, max_runtime_seconds=1)
    assert result["ok"] is False
    assert result["timed_out"] is True


def test_run_job_once_reports_exception():
    def failing_job():
        raise ValueError("boom")

    result = _run_job_once(failing_job, max_runtime_seconds=5)
    assert result["ok"] is False
    assert result["timed_out"] is False
    assert "ValueError" in str(result["reason"])
