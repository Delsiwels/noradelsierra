"""Pytest configuration and shared fixtures."""

import pytest


@pytest.fixture(scope="function")
def app():
    """Create test Flask app with proper context handling."""
    from webapp.app import create_app
    from webapp.config import TestingConfig

    app = create_app(TestingConfig)
    app.config["TESTING"] = True

    with app.app_context():
        from webapp.models import db

        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def db(app):
    """Get database instance."""
    from webapp.models import db as _db

    return _db
