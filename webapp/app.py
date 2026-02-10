"""Main Flask application."""

import importlib
import logging
import os
from datetime import timedelta

from flask import Flask, jsonify, request
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate

from webapp.ai import init_ai_client, init_chat_service
from webapp.ai.token_tracker import init_token_tracker
from webapp.blueprints.analytics import analytics_bp
from webapp.blueprints.auth import auth_bp
from webapp.blueprints.cashflow import cashflow_bp
from webapp.blueprints.chat import chat_bp
from webapp.blueprints.forecast import forecast_bp
from webapp.blueprints.pages import pages_bp
from webapp.blueprints.skills import skills_bp
from webapp.blueprints.usage import usage_bp
from webapp.config import Config
from webapp.models import User, db
from webapp.routes import api_bp
from webapp.services.background_jobs import ManagedJob, start_background_scheduler
from webapp.services.maintenance import (
    cleanup_expired_conversations,
    snapshot_runtime_health,
)
from webapp.services.operational_alerts import send_operational_alert
from webapp.services.runtime_health import runtime_health
from webapp.services.runtime_health_persistence import (
    list_runtime_health_snapshots,
)
from webapp.services.startup_checks import (
    build_readiness_report,
    run_startup_config_audit,
    should_fail_fast_on_config_audit,
)
from webapp.skills.analytics_service import init_analytics_service
from webapp.skills.r2_skill_loader import init_r2_loader

logger = logging.getLogger(__name__)

bcrypt = Bcrypt()
login_manager = LoginManager()
migrate = Migrate()


@login_manager.user_loader
def load_user(user_id: str):
    """Load user by ID for Flask-Login."""
    return User.query.get(user_id)


@login_manager.unauthorized_handler
def unauthorized():
    """Handle unauthorized access."""
    return jsonify({"error": "Authentication required"}), 401


def _register_optional_blueprint(
    app: Flask,
    module_path: str,
    blueprint_name: str,
) -> bool:
    """Register a blueprint if module + symbol are available."""
    try:
        module = importlib.import_module(module_path)
        blueprint = getattr(module, blueprint_name)
        app.register_blueprint(blueprint)
        return True
    except ModuleNotFoundError as exc:
        logger.warning(
            "Skipping optional blueprint %s.%s (%s)",
            module_path,
            blueprint_name,
            exc,
        )
    except AttributeError:
        logger.warning(
            "Skipping optional blueprint %s: missing symbol '%s'",
            module_path,
            blueprint_name,
        )
    except Exception:
        logger.exception(
            "Failed to register optional blueprint %s.%s",
            module_path,
            blueprint_name,
        )
    return False


def create_app(config_class: type = Config) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    config_audit = run_startup_config_audit(app)
    app.extensions["startup_config_audit"] = config_audit
    runtime_health.set_startup_config_audit(config_audit)

    for warning in config_audit.get("warnings", []):
        logger.warning("Startup config warning: %s", warning)
    for error in config_audit.get("errors", []):
        logger.error("Startup config issue: %s", error)
    if config_audit.get("errors"):
        send_operational_alert(
            app,
            event_type="startup_config_audit",
            severity="high",
            message="Startup config audit found errors.",
            details={"errors": config_audit["errors"]},
            dedupe_key="startup_config_audit_errors",
        )
    if config_audit.get("errors") and should_fail_fast_on_config_audit(app):
        raise RuntimeError(
            "Startup config audit failed with errors: "
            + "; ".join(config_audit["errors"])
        )

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db, directory="migrations")

    # Session config
    app.permanent_session_lifetime = timedelta(
        seconds=app.config.get("PERMANENT_SESSION_LIFETIME", 86400)
    )

    # Keep bootstrap table creation for fresh ephemeral environments.
    with app.app_context():
        db.create_all()

    # Initialize R2 skill loader
    init_r2_loader(app)

    # Initialize AI client and chat service
    init_ai_client(app)
    init_chat_service(app)

    # Initialize token tracker
    init_token_tracker(app)

    # Initialize analytics service
    init_analytics_service(app)

    # Register blueprints
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(skills_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(usage_bp)
    app.register_blueprint(cashflow_bp)
    app.register_blueprint(forecast_bp)

    # Import and register Phase 2-5 blueprints
    from webapp.blueprints.sharing import sharing_bp

    app.register_blueprint(sharing_bp)

    from webapp.blueprints.export import export_bp

    app.register_blueprint(export_bp)

    from webapp.blueprints.reminders import reminders_bp

    app.register_blueprint(reminders_bp)

    from webapp.blueprints.readiness import readiness_bp

    app.register_blueprint(readiness_bp)

    from webapp.blueprints.connections import connections_bp

    app.register_blueprint(connections_bp)

    _register_optional_blueprint(app, "webapp.blueprints.ask_fin", "ask_fin_bp")

    from webapp.blueprints.payroll_review import payroll_review_bp

    app.register_blueprint(payroll_review_bp)

    # Quarter-End Readiness Features
    from webapp.blueprints.aging_dashboard import aging_dashboard_bp
    from webapp.blueprints.bank_recon_status import bank_recon_status_bp
    from webapp.blueprints.budget_actual import budget_actual_bp
    from webapp.blueprints.depreciation_calc import depreciation_calc_bp
    from webapp.blueprints.fuel_tax_credits import fuel_tax_credits_bp
    from webapp.blueprints.payg_instalment import payg_instalment_bp
    from webapp.blueprints.payg_reconciliation import payg_reconciliation_bp
    from webapp.blueprints.payroll_tax import payroll_tax_bp
    from webapp.blueprints.prepayment_tracker import prepayment_tracker_bp
    from webapp.blueprints.stp_tracker import stp_tracker_bp

    app.register_blueprint(payg_reconciliation_bp)
    app.register_blueprint(aging_dashboard_bp)
    app.register_blueprint(bank_recon_status_bp)
    app.register_blueprint(depreciation_calc_bp)
    app.register_blueprint(payg_instalment_bp)
    app.register_blueprint(stp_tracker_bp)
    app.register_blueprint(payroll_tax_bp)
    app.register_blueprint(budget_actual_bp)
    app.register_blueprint(prepayment_tracker_bp)
    app.register_blueprint(fuel_tax_credits_bp)

    scheduler_report = start_background_scheduler(
        app,
        jobs=[
            ManagedJob(
                job_id="cleanup_expired_conversations",
                func=lambda: cleanup_expired_conversations(app),
                cron_env_var="CLEANUP_CONVERSATIONS_CRON",
                interval_env_var="CLEANUP_CONVERSATIONS_MINUTES",
                default_interval_minutes=60,
                fallback_minute=0,
                max_runtime_seconds=300,
                max_retries=1,
                retry_backoff_seconds=2.0,
            ),
            ManagedJob(
                job_id="persist_runtime_health_snapshot",
                func=lambda: snapshot_runtime_health(app),
                cron_env_var="RUNTIME_HEALTH_SNAPSHOT_CRON",
                interval_env_var="RUNTIME_HEALTH_SNAPSHOT_MINUTES",
                default_interval_minutes=15,
                fallback_minute=5,
                max_runtime_seconds=60,
                max_retries=0,
                retry_backoff_seconds=1.0,
            ),
        ],
    )
    app.extensions["runtime_scheduler_state"] = {
        "enabled": scheduler_report.enabled,
        "started": scheduler_report.started,
        "warnings": scheduler_report.warnings,
    }

    @app.route("/health")
    def health_check():
        """Health check endpoint."""
        runtime_report = runtime_health.build_report(app)
        return jsonify(
            {
                "status": "healthy",
                "version": "0.3.0",
                "scheduler_enabled": runtime_report["scheduler"]["enabled"],
                "scheduler_started": runtime_report["scheduler"]["started"],
            }
        )

    @app.route("/health/ready")
    def readiness_check():
        """Readiness endpoint that verifies DB, migrations, and startup config."""
        report = build_readiness_report(
            app,
            app.extensions.get("startup_config_audit", {"warnings": [], "errors": []}),
        )
        return jsonify(report), (200 if report["ready"] else 503)

    @app.route("/health/runtime")
    def runtime_health_check():
        """Runtime operational health report."""
        return jsonify(runtime_health.build_report(app))

    @app.route("/health/runtime/snapshots")
    def runtime_health_snapshots():
        """Latest persisted runtime health snapshots."""
        try:
            limit = int(request.args.get("limit", "25"))
        except ValueError:
            limit = 25
        snapshots = list_runtime_health_snapshots(limit)
        return jsonify({"count": len(snapshots), "snapshots": snapshots})

    # Register CLI commands for maintenance tasks
    @app.cli.command("cleanup-conversations")
    def cleanup_conversations_command():
        """Remove expired conversations (30-day retention)."""
        count = cleanup_expired_conversations(app)
        print(f"Deleted {count} expired conversations")

    @app.cli.command("snapshot-runtime-health")
    def snapshot_runtime_health_command():
        """Persist one runtime health snapshot now."""
        snapshot_id = snapshot_runtime_health(app)
        print(f"Snapshot created: {snapshot_id}")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
