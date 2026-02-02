"""Main Flask application."""

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
from webapp.blueprints.pages import pages_bp
from webapp.blueprints.skills import skills_bp
from webapp.blueprints.usage import usage_bp
from webapp.config import Config
from webapp.models import Conversation, User, db
from webapp.routes import api_bp
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

    # Create tables in development mode
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

    # Import and register Phase 2-5 blueprints
    from webapp.blueprints.sharing import sharing_bp

    app.register_blueprint(sharing_bp)

    from webapp.blueprints.export import export_bp

    app.register_blueprint(export_bp)

    from webapp.blueprints.reminders import reminders_bp

    app.register_blueprint(reminders_bp)

    from webapp.blueprints.readiness import readiness_bp

    app.register_blueprint(readiness_bp)

    @app.route("/health")
    def health_check():
        """Health check endpoint."""
        return jsonify({"status": "healthy", "version": "0.3.0"})

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
