"""Startup validation and readiness checks."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import Flask
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text

from webapp.models import db

_DEV_CONFIG_SENTINEL = "dev-" + "key-change-in-production"


@dataclass(frozen=True)
class LightweightMigration:
    """Describes a lightweight schema patch that can run at startup."""

    identifier: str
    table_name: str
    column_name: str
    alter_sql: str


LIGHTWEIGHT_MIGRATIONS = [
    LightweightMigration(
        identifier="checklist_progress.tenant_id",
        table_name="checklist_progress",
        column_name="tenant_id",
        alter_sql=(
            "ALTER TABLE checklist_progress " "ADD COLUMN tenant_id VARCHAR(255)"
        ),
    ),
    LightweightMigration(
        identifier="checklist_progress.tenant_name",
        table_name="checklist_progress",
        column_name="tenant_name",
        alter_sql=(
            "ALTER TABLE checklist_progress " "ADD COLUMN tenant_name VARCHAR(255)"
        ),
    ),
    LightweightMigration(
        identifier="users.bas_lodge_method",
        table_name="users",
        column_name="bas_lodge_method",
        alter_sql=(
            "ALTER TABLE users "
            "ADD COLUMN bas_lodge_method VARCHAR(10) DEFAULT 'self'"
        ),
    ),
]


def get_pending_lightweight_migrations() -> list[LightweightMigration]:
    """Return lightweight schema patches that are still pending."""
    inspector = sa_inspect(db.engine)
    pending: list[LightweightMigration] = []

    for migration in LIGHTWEIGHT_MIGRATIONS:
        if not inspector.has_table(migration.table_name):
            continue
        existing_columns = {
            column["name"] for column in inspector.get_columns(migration.table_name)
        }
        if migration.column_name not in existing_columns:
            pending.append(migration)

    return pending


def apply_lightweight_migrations() -> dict[str, list[str]]:
    """Apply pending lightweight schema patches."""
    applied: list[str] = []
    failed: list[str] = []

    for migration in get_pending_lightweight_migrations():
        try:
            db.session.execute(text(migration.alter_sql))
            db.session.commit()
            applied.append(migration.identifier)
        except Exception as exc:
            db.session.rollback()
            failed.append(f"{migration.identifier}: {type(exc).__name__}: {exc}")

    return {"applied": applied, "failed": failed}


def get_alembic_revision_status(app: Flask) -> dict[str, Any]:
    """Return Alembic revision status for readiness checks."""
    try:
        from alembic.config import Config as AlembicConfig
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
    except Exception as exc:
        return {
            "ok": False,
            "available": False,
            "detail": f"Alembic unavailable: {type(exc).__name__}: {exc}",
            "current_heads": [],
            "target_heads": [],
            "pending_heads": [],
        }

    script_location = str(app.config.get("ALEMBIC_SCRIPT_LOCATION", "migrations"))
    if not Path(script_location).exists():
        return {
            "ok": False,
            "available": False,
            "detail": f"Migration directory not found: {script_location}",
            "current_heads": [],
            "target_heads": [],
            "pending_heads": [],
        }

    try:
        alembic_cfg = AlembicConfig()
        alembic_cfg.set_main_option("script_location", script_location)
        script = ScriptDirectory.from_config(alembic_cfg)
        target_heads = list(script.get_heads())

        with db.engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_heads = list(context.get_current_heads() or [])
    except Exception as exc:
        return {
            "ok": False,
            "available": True,
            "detail": f"Failed to inspect Alembic revisions: {type(exc).__name__}: {exc}",
            "current_heads": [],
            "target_heads": [],
            "pending_heads": [],
        }

    if app.config.get("TESTING"):
        return {
            "ok": True,
            "available": True,
            "detail": "Skipped strict Alembic head enforcement in testing context.",
            "current_heads": current_heads,
            "target_heads": target_heads,
            "pending_heads": [],
        }

    pending_heads = sorted(set(target_heads) - set(current_heads))
    return {
        "ok": len(pending_heads) == 0,
        "available": True,
        "detail": "",
        "current_heads": current_heads,
        "target_heads": target_heads,
        "pending_heads": pending_heads,
    }


def db_connectivity_check() -> dict[str, Any]:
    """Check that the app can execute a simple query."""
    try:
        db.session.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception as exc:
        db.session.rollback()
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}


def run_startup_config_audit(app: Flask) -> dict[str, list[str]]:
    """Audit critical startup settings and return warnings/errors."""
    warnings: list[str] = []
    errors: list[str] = []

    is_production = _is_production_context(app)
    secret_key = app.config.get("SECRET_KEY")
    if not secret_key or secret_key == _DEV_CONFIG_SENTINEL:  # noqa: S105
        message = "SECRET_KEY is using a development default."
        if is_production:
            errors.append(message)
        else:
            warnings.append(message)

    database_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if is_production and str(database_uri).startswith("sqlite:///"):
        errors.append(
            "SQLALCHEMY_DATABASE_URI is using local sqlite in production context."
        )

    ai_provider = str(app.config.get("AI_PROVIDER", "anthropic")).lower()
    if ai_provider == "anthropic" and not app.config.get("ANTHROPIC_API_KEY"):
        warnings.append("AI provider is anthropic but ANTHROPIC_API_KEY is not set.")
    if ai_provider == "openai" and not app.config.get("OPENAI_API_KEY"):
        warnings.append("AI provider is openai but OPENAI_API_KEY is not set.")
    if ai_provider == "deepseek" and not app.config.get("DEEPSEEK_API_KEY"):
        warnings.append("AI provider is deepseek but DEEPSEEK_API_KEY is not set.")

    if app.config.get("R2_STORAGE_ENABLED"):
        missing_r2 = [
            key
            for key in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
            if not app.config.get(key)
        ]
        if missing_r2:
            warnings.append(
                "R2 storage is enabled but missing credentials: "
                + ", ".join(missing_r2)
            )

    alerts_enabled = bool(app.config.get("OP_ALERTS_ENABLED", False))
    if alerts_enabled:
        has_webhook = bool(app.config.get("OP_ALERT_WEBHOOK_URL")) or bool(
            app.config.get("OP_ALERT_SLACK_WEBHOOK_URL")
        )
        has_email = bool(app.config.get("OP_ALERT_EMAIL_TO")) and bool(
            app.config.get("SMTP_HOST")
        )
        if not has_webhook and not has_email:
            errors.append(
                "OP_ALERTS_ENABLED is true but no webhook or SMTP email channel is configured."
            )

    return {"warnings": warnings, "errors": errors}


def build_readiness_report(
    app: Flask, config_audit: dict[str, list[str]]
) -> dict[str, Any]:
    """Build readiness state from DB, migration, and startup audit checks."""
    db_check = db_connectivity_check()
    pending_migrations = [m.identifier for m in get_pending_lightweight_migrations()]
    alembic_status = get_alembic_revision_status(app)

    scheduler = app.extensions.get("runtime_scheduler_state", {})
    scheduler_enabled = bool(scheduler.get("enabled"))
    scheduler_started = bool(scheduler.get("started"))
    scheduler_ok = (not scheduler_enabled) or scheduler_started

    checks = {
        "db_connectivity": db_check,
        "lightweight_migrations": {
            "ok": len(pending_migrations) == 0,
            "pending": pending_migrations,
            "detail": (
                "Pending additive schema patches detected. Run Alembic upgrades before deployment."
                if pending_migrations
                else ""
            ),
        },
        "alembic": alembic_status,
        "startup_config": {
            "ok": len(config_audit.get("errors", [])) == 0,
            "warnings": list(config_audit.get("warnings", [])),
            "errors": list(config_audit.get("errors", [])),
        },
        "scheduler": {
            "ok": scheduler_ok,
            "enabled": scheduler_enabled,
            "started": scheduler_started,
        },
    }

    ready = (
        checks["db_connectivity"]["ok"]
        and checks["lightweight_migrations"]["ok"]
        and checks["alembic"]["ok"]
        and checks["startup_config"]["ok"]
        and checks["scheduler"]["ok"]
    )
    return {
        "ready": ready,
        "status": "ready" if ready else "not_ready",
        "checks": checks,
    }


def should_fail_fast_on_config_audit(app: Flask) -> bool:
    """True when startup should fail on config audit errors."""
    return bool(app.config.get("STARTUP_CONFIG_AUDIT_FAIL_FAST", False))


def _is_production_context(app: Flask) -> bool:
    if app.config.get("TESTING"):
        return False
    if app.config.get("DEBUG"):
        return False

    explicit_env = (
        os.getenv("FLASK_ENV")
        or os.getenv("APP_ENV")
        or os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RAILWAY_ENVIRONMENT_NAME")
        or ""
    )
    if explicit_env.lower() == "production":
        return True
    if explicit_env.lower() in {"development", "dev", "test", "testing"}:
        return False

    if os.getenv("RAILWAY_PROJECT_ID"):
        return True

    return False
