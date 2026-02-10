"""Main Flask application."""

import importlib
import logging
import os
from datetime import datetime, timedelta

from flask import Flask, jsonify
from flask_bcrypt import Bcrypt
from flask_login import LoginManager

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
from webapp.models import Conversation, User, db
from webapp.routes import api_bp
from webapp.services.background_jobs import ManagedJob, start_background_scheduler
from webapp.services.runtime_health import runtime_health
from webapp.skills.analytics_service import init_analytics_service
from webapp.skills.r2_skill_loader import init_r2_loader

logger = logging.getLogger(__name__)

bcrypt = Bcrypt()
login_manager = LoginManager()


@login_manager.user_loader
def load_user(user_id: str):
    """Load user by ID for Flask-Login."""
    return User.query.get(user_id)


@login_manager.unauthorized_handler
def unauthorized():
    """Handle unauthorized access."""
    return jsonify({"error": "Authentication required"}), 401


def cleanup_expired_conversations(app: Flask) -> int:
    """
    Delete conversations that have expired (past expires_at date).

    Args:
        app: Flask application instance

    Returns:
        Number of conversations deleted
    """
    with app.app_context():
        now = datetime.utcnow()

        # Find and delete expired conversations
        expired = Conversation.query.filter(Conversation.expires_at <= now).all()

        count = len(expired)

        for conversation in expired:
            db.session.delete(conversation)

        if count > 0:
            db.session.commit()
            logger.info(f"Cleaned up {count} expired conversations")

        return count


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

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)

    # Session config
    app.permanent_session_lifetime = timedelta(
        seconds=app.config.get("PERMANENT_SESSION_LIFETIME", 86400)
    )

    # Create tables and run lightweight migrations
    with app.app_context():
        db.create_all()

        # Migration: add tenant_id / tenant_name to checklist_progress
        from sqlalchemy import inspect as sa_inspect
        from sqlalchemy import text

        insp = sa_inspect(db.engine)
        if insp.has_table("checklist_progress"):
            existing_cols = {c["name"] for c in insp.get_columns("checklist_progress")}
            if "tenant_id" not in existing_cols:
                try:
                    db.session.execute(
                        text(
                            "ALTER TABLE checklist_progress "
                            "ADD COLUMN tenant_id VARCHAR(255)"
                        )
                    )
                    db.session.commit()
                    logger.info("Added tenant_id column to checklist_progress")
                except Exception:
                    db.session.rollback()
            if "tenant_name" not in existing_cols:
                try:
                    db.session.execute(
                        text(
                            "ALTER TABLE checklist_progress "
                            "ADD COLUMN tenant_name VARCHAR(255)"
                        )
                    )
                    db.session.commit()
                    logger.info("Added tenant_name column to checklist_progress")
                except Exception:
                    db.session.rollback()

        # Migration: add bas_lodge_method to users
        if insp.has_table("users"):
            user_cols = {c["name"] for c in insp.get_columns("users")}
            if "bas_lodge_method" not in user_cols:
                try:
                    db.session.execute(
                        text(
                            "ALTER TABLE users "
                            "ADD COLUMN bas_lodge_method VARCHAR(10) DEFAULT 'self'"
                        )
                    )
                    db.session.commit()
                    logger.info("Added bas_lodge_method column to users")
                except Exception:
                    db.session.rollback()

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

    start_background_scheduler(
        app,
        jobs=[
            ManagedJob(
                job_id="cleanup_expired_conversations",
                func=lambda: cleanup_expired_conversations(app),
                cron_env_var="CLEANUP_CONVERSATIONS_CRON",
                interval_env_var="CLEANUP_CONVERSATIONS_MINUTES",
                default_interval_minutes=60,
                fallback_minute=0,
            )
        ],
    )

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

    @app.route("/health/runtime")
    def runtime_health_check():
        """Runtime operational health report."""
        return jsonify(runtime_health.build_report(app))

    # Register CLI commands for maintenance tasks
    @app.cli.command("cleanup-conversations")
    def cleanup_conversations_command():
        """Remove expired conversations (30-day retention)."""
        count = cleanup_expired_conversations(app)
        print(f"Deleted {count} expired conversations")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
