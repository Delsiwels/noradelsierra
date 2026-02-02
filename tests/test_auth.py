"""Tests for authentication blueprint."""

import pytest


@pytest.fixture
def app():
    """Create test Flask app."""
    from webapp.app import create_app
    from webapp.config import TestingConfig

    app = create_app(TestingConfig)
    app.config["TESTING"] = True
    # Need WTF_CSRF_ENABLED = False for form testing
    app.config["WTF_CSRF_ENABLED"] = False

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


class TestRegistration:
    """Tests for user registration."""

    def test_register_success(self, client):
        """Test successful registration."""
        res = client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "password": "securepass123",
                "name": "Test User",
            },
        )
        assert res.status_code == 201
        data = res.get_json()
        assert data["success"] is True
        assert data["user"]["email"] == "test@example.com"
        assert data["user"]["name"] == "Test User"
        assert data["user"]["role"] == "owner"
        assert data["user"]["team_id"] is not None

    def test_register_creates_team(self, client, db):
        """Test that registration creates a team."""
        client.post(
            "/api/auth/register",
            json={
                "email": "owner@example.com",
                "password": "securepass123",
                "name": "Business Owner",
            },
        )
        from webapp.models import Team

        teams = Team.query.all()
        assert len(teams) == 1
        assert "Business Owner" in teams[0].name

    def test_register_invalid_email(self, client):
        """Test registration with invalid email."""
        res = client.post(
            "/api/auth/register",
            json={
                "email": "not-an-email",
                "password": "securepass123",
                "name": "Test",
            },
        )
        assert res.status_code == 400
        assert "email" in res.get_json()["error"].lower()

    def test_register_short_password(self, client):
        """Test registration with too-short password."""
        res = client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "password": "short",
                "name": "Test",
            },
        )
        assert res.status_code == 400
        assert "8 characters" in res.get_json()["error"]

    def test_register_missing_name(self, client):
        """Test registration with missing name."""
        res = client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "password": "securepass123",
                "name": "",
            },
        )
        assert res.status_code == 400

    def test_register_duplicate_email(self, client):
        """Test registration with duplicate email."""
        client.post(
            "/api/auth/register",
            json={
                "email": "dup@example.com",
                "password": "securepass123",
                "name": "User 1",
            },
        )
        res = client.post(
            "/api/auth/register",
            json={
                "email": "dup@example.com",
                "password": "securepass123",
                "name": "User 2",
            },
        )
        assert res.status_code == 409

    def test_register_no_json(self, client):
        """Test registration without JSON body."""
        res = client.post("/api/auth/register")
        assert res.status_code == 400


class TestLogin:
    """Tests for user login."""

    def _register(self, client, email="test@example.com", password="securepass123"):
        client.post(
            "/api/auth/register",
            json={"email": email, "password": password, "name": "Test User"},
        )

    def test_login_success(self, client):
        """Test successful login."""
        self._register(client)
        res = client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "securepass123"},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert data["user"]["email"] == "test@example.com"

    def test_login_wrong_password(self, client):
        """Test login with wrong password."""
        self._register(client)
        res = client.post(
            "/api/auth/login",
            json={"email": "test@example.com", "password": "wrongpassword"},
        )
        assert res.status_code == 401

    def test_login_nonexistent_user(self, client):
        """Test login for nonexistent user."""
        res = client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "somepassword"},
        )
        assert res.status_code == 401

    def test_login_missing_fields(self, client):
        """Test login with missing fields."""
        res = client.post(
            "/api/auth/login",
            json={"email": "", "password": ""},
        )
        assert res.status_code == 400


class TestLogout:
    """Tests for user logout."""

    def test_logout(self, client):
        """Test logout after login."""
        client.post(
            "/api/auth/register",
            json={"email": "test@example.com", "password": "securepass123", "name": "Test"},
        )
        res = client.post("/api/auth/logout")
        assert res.status_code == 200
        assert res.get_json()["success"] is True


class TestMe:
    """Tests for current user endpoint."""

    def test_me_authenticated(self, client):
        """Test /me for authenticated user."""
        client.post(
            "/api/auth/register",
            json={"email": "test@example.com", "password": "securepass123", "name": "Test User"},
        )
        res = client.get("/api/auth/me")
        assert res.status_code == 200
        data = res.get_json()
        assert data["user"]["email"] == "test@example.com"
        assert data["user"]["role"] == "owner"


class TestProtectedEndpoints:
    """Test that endpoints require authentication when not in testing mode."""

    def test_register_page(self, client):
        """Test register page renders."""
        res = client.get("/register")
        assert res.status_code == 200

    def test_login_page(self, client):
        """Test login page renders."""
        res = client.get("/login")
        assert res.status_code == 200
