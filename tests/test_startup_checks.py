"""Tests for startup checks and readiness endpoints."""

import uuid

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
    assert any(
        "*/60" in warning for warning in runtime_payload["scheduler"]["warnings"]
    )


def test_runtime_health_includes_optional_blueprint_status(client):
    payload = client.get("/health/runtime").get_json()
    optional = payload["optional_blueprints"]

    assert "webapp.blueprints.ask_fin.ask_fin_bp" in optional
    assert isinstance(optional["webapp.blueprints.ask_fin.ask_fin_bp"], bool)


def test_alembic_status_ready_for_bootstrapped_db():
    """A fresh create_all() DB (no Alembic stamp) is ready, not 'pending'."""
    from webapp.app import create_app
    from webapp.config import TestingConfig
    from webapp.services.startup_checks import get_alembic_revision_status

    class _NonTestingConfig(TestingConfig):
        TESTING = False  # exercise the strict (non-testing) Alembic branch

    app = create_app(_NonTestingConfig)
    with app.app_context():
        status = get_alembic_revision_status(app)

    assert status["available"] is True
    assert status["current_heads"] == []  # bootstrapped, never stamped
    assert status["pending_heads"] == []
    assert status["ok"] is True


def test_health_ready_ok_for_bootstrapped_db(monkeypatch):
    """/health/ready returns 200 on a fresh create_all DB (deploy-smoke case)."""
    monkeypatch.setenv("ENABLE_BACKGROUND_JOBS", "false")
    from webapp.app import create_app
    from webapp.config import TestingConfig

    class _NonTestingConfig(TestingConfig):
        TESTING = False

    app = create_app(_NonTestingConfig)
    response = app.test_client().get("/health/ready")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ready"] is True
    assert payload["checks"]["alembic"]["ok"] is True


def test_health_ready_reports_not_ready_when_migration_directory_missing(app):
    app.config["ALEMBIC_SCRIPT_LOCATION"] = f"nonexistent-migrations-{uuid.uuid4()}"

    client = app.test_client()
    response = client.get("/health/ready")

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["ready"] is False
    assert payload["checks"]["alembic"]["ok"] is False
    assert payload["checks"]["alembic"]["available"] is False
