"""Tests for startup checks and readiness endpoints."""

from flask import Flask

from webapp.services.startup_checks import run_startup_config_audit


def test_startup_config_audit_flags_production_defaults(monkeypatch):
    app = Flask(__name__)
    app.config["TESTING"] = False
    app.config["DEBUG"] = False
    app.config["SECRET_KEY"] = "dev-key-change-in-production"  # noqa: S105
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
    app.config["AI_PROVIDER"] = "anthropic"
    app.config["ANTHROPIC_API_KEY"] = None
    app.config["R2_STORAGE_ENABLED"] = False
    app.config["OP_ALERTS_ENABLED"] = False

    monkeypatch.setenv("FLASK_ENV", "production")
    result = run_startup_config_audit(app)
    assert any("SECRET_KEY" in error for error in result["errors"])
    assert any("SQLALCHEMY_DATABASE_URI" in error for error in result["errors"])


def test_health_ready_endpoint_reports_ready(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ready"] is True
    assert payload["checks"]["db_connectivity"]["ok"] is True


def test_invalid_cron_falls_back_without_boot_failure(monkeypatch):
    from webapp.app import create_app
    from webapp.config import TestingConfig

    monkeypatch.setenv("ENABLE_BACKGROUND_JOBS", "true")
    monkeypatch.setenv("CLEANUP_CONVERSATIONS_CRON", "*/60")
    monkeypatch.setenv("RUNTIME_HEALTH_SNAPSHOT_ENABLED", "false")

    app = create_app(TestingConfig)
    client = app.test_client()
    runtime_payload = client.get("/health/runtime").get_json()

    assert runtime_payload["scheduler"]["enabled"] is True
    assert any("*/60" in warning for warning in runtime_payload["scheduler"]["warnings"])
