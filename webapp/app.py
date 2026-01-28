"""Main Flask application."""

import os

from flask import Flask, jsonify

from webapp.ai import init_ai_client, init_chat_service
from webapp.blueprints.chat import chat_bp
from webapp.blueprints.skills import skills_bp
from webapp.config import Config
from webapp.models import db
from webapp.routes import api_bp
from webapp.skills.r2_skill_loader import init_r2_loader


def create_app(config_class: type = Config) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize SQLAlchemy
    db.init_app(app)

    # Create tables in development mode
    with app.app_context():
        db.create_all()

    # Initialize R2 skill loader
    init_r2_loader(app)

    # Initialize AI client and chat service
    init_ai_client(app)
    init_chat_service(app)

    # Register blueprints
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(skills_bp)
    app.register_blueprint(chat_bp)

    @app.route("/health")
    def health_check():
        """Health check endpoint."""
        return jsonify({"status": "healthy", "version": "0.1.0"})

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
