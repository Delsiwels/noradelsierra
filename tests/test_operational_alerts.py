"""Tests for operational alert delivery telemetry."""

from webapp.services.operational_alerts import (
    get_operational_alert_telemetry,
    reset_operational_alert_telemetry,
    send_operational_alert,
)


def test_alert_telemetry_records_suppressed_when_alerting_disabled(app):
    app.config["OP_ALERTS_ENABLED"] = False
    reset_operational_alert_telemetry()

    sent = send_operational_alert(
        app,
        event_type="runtime_health_degraded",
        severity="high",
        message="Runtime degraded.",
        dedupe_key="disabled-case",
    )
    assert sent is False

    telemetry = get_operational_alert_telemetry()
    assert telemetry["counts"]["attempted"] == 0
    assert telemetry["counts"]["suppressed"] == 1
    assert telemetry["recent"][0]["status"] == "suppressed"


def test_alert_telemetry_records_delivery_and_cooldown_suppression(app, monkeypatch):
    app.config["OP_ALERTS_ENABLED"] = True
    app.config["OP_ALERT_WEBHOOK_URL"] = "https://example.test/hook"
    app.config["OP_ALERT_COOLDOWN_SECONDS"] = 3600
    reset_operational_alert_telemetry()

    monkeypatch.setattr(
        "webapp.services.operational_alerts._post_json",
        lambda _url, _payload: True,
    )

    first = send_operational_alert(
        app,
        event_type="scheduler_boot",
        severity="medium",
        message="Scheduler started",
        dedupe_key="boot-alert",
    )
    second = send_operational_alert(
        app,
        event_type="scheduler_boot",
        severity="medium",
        message="Scheduler started",
        dedupe_key="boot-alert",
    )

    assert first is True
    assert second is False

    telemetry = get_operational_alert_telemetry()
    assert telemetry["counts"]["attempted"] == 1
    assert telemetry["counts"]["delivered"] == 1
    assert telemetry["counts"]["suppressed"] == 1
    assert telemetry["channels"]["webhook"]["attempted"] == 1
    assert telemetry["channels"]["webhook"]["delivered"] == 1
