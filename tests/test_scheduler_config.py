"""Tests for scheduler configuration safety guards."""

from webapp.services.scheduler_config import resolve_job_schedule


def test_default_hourly_interval_resolves_without_warning():
    result = resolve_job_schedule(
        job_name="cleanup_expired_conversations",
        cron_value=None,
        interval_value=None,
        default_interval_minutes=60,
    )

    assert result.cron_expression == "0 * * * *"
    assert result.warning is None


def test_interval_sixty_falls_back_and_warns():
    result = resolve_job_schedule(
        job_name="cleanup_expired_conversations",
        cron_value=None,
        interval_value="60",
        default_interval_minutes=30,
    )

    assert result.cron_expression == "0 * * * *"
    assert result.warning is not None
    assert "invalid for minute range 0-59" in result.warning


def test_explicit_invalid_minute_step_falls_back():
    result = resolve_job_schedule(
        job_name="cleanup_expired_conversations",
        cron_value="*/60",
        interval_value=None,
    )

    assert result.cron_expression == "0 * * * *"
    assert result.warning is not None
    assert "minute expression '*/60'" in result.warning


def test_explicit_full_cron_sanitizes_only_minute_field():
    result = resolve_job_schedule(
        job_name="cleanup_expired_conversations",
        cron_value="*/60 1 * * 1-5",
        interval_value=None,
    )

    assert result.cron_expression == "0 1 * * 1-5"
    assert result.warning is not None


def test_valid_interval_uses_step_cron():
    result = resolve_job_schedule(
        job_name="cleanup_expired_conversations",
        cron_value=None,
        interval_value="15",
    )

    assert result.cron_expression == "*/15 * * * *"
    assert result.warning is None


def test_invalid_interval_text_falls_back():
    result = resolve_job_schedule(
        job_name="cleanup_expired_conversations",
        cron_value=None,
        interval_value="abc",
    )

    assert result.cron_expression == "0 * * * *"
    assert result.warning is not None
