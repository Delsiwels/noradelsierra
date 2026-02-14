"""Tests for Xero connections blueprint."""

from urllib.parse import parse_qs, urlparse

import pytest


@pytest.fixture
def app():
    """Create test Flask app."""
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


def _register_and_login(client):
    """Helper to register and log in a test user."""
    client.post(
        "/api/auth/register",
        json={
            "email": "conn@example.com",
            "password": "securepass123",
            "name": "Conn User",
        },
    )


class TestConnectionStatus:
    """Tests for GET /api/connection-status."""

    def test_requires_auth(self, client):
        """Unauthenticated requests return 401."""
        res = client.get("/api/connection-status")
        assert res.status_code == 401

    def test_disconnected_by_default(self, client):
        """New user has no Xero connection."""
        _register_and_login(client)
        res = client.get("/api/connection-status")
        assert res.status_code == 200
        data = res.get_json()
        assert data["connected"] is False
        assert data["status"] == "disconnected"
        assert data["tenant_name"] is None
        assert data["tenant_id"] is None

    def test_healthy_connection(self, client):
        """Session with valid token reports healthy."""
        _register_and_login(client)
        with client.session_transaction() as sess:
            sess["xero_connection"] = {
                "access_token": "tok_123",
                "tenant_id": "tid_1",
                "tenant_name": "Demo Company AU",
                "token_expires_at": "2099-01-01T00:00:00+00:00",
            }
        res = client.get("/api/connection-status")
        data = res.get_json()
        assert data["connected"] is True
        assert data["status"] == "healthy"
        assert data["tenant_name"] == "Demo Company AU"
        assert data["tenant_id"] == "tid_1"

    def test_expired_connection(self, client):
        """Session with expired token reports expired."""
        _register_and_login(client)
        with client.session_transaction() as sess:
            sess["xero_connection"] = {
                "access_token": "tok_old",
                "tenant_id": "tid_1",
                "tenant_name": "Old Org",
                "token_expires_at": "2020-01-01T00:00:00+00:00",
            }
        res = client.get("/api/connection-status")
        data = res.get_json()
        assert data["connected"] is False
        assert data["status"] == "expired"


class TestListConnections:
    """Tests for GET /xero/api/connections."""

    def test_requires_auth(self, client):
        res = client.get("/xero/api/connections")
        assert res.status_code == 401

    def test_empty_by_default(self, client):
        """No tenants stored returns empty list."""
        _register_and_login(client)
        res = client.get("/xero/api/connections")
        data = res.get_json()
        assert data["connections"] == []

    def test_returns_tenants(self, client):
        """Stored tenants are listed with active flag."""
        _register_and_login(client)
        with client.session_transaction() as sess:
            sess["xero_connection"] = {
                "access_token": "tok",
                "tenant_id": "tid_1",
                "tenant_name": "Demo Company",
            }
            sess["xero_tenants"] = [
                {"tenant_id": "tid_1", "tenant_name": "Demo Company"},
                {"tenant_id": "tid_2", "tenant_name": "Other Org"},
            ]
        res = client.get("/xero/api/connections")
        data = res.get_json()
        conns = data["connections"]
        assert len(conns) == 2
        assert conns[0]["is_active"] is True
        assert conns[0]["tenant_name"] == "Demo Company"
        assert conns[1]["is_active"] is False
        assert conns[1]["tenant_name"] == "Other Org"

    def test_fallback_to_active_connection(self, client):
        """If no tenants list but active connection exists, return it."""
        _register_and_login(client)
        with client.session_transaction() as sess:
            sess["xero_connection"] = {
                "access_token": "tok",
                "tenant_id": "tid_1",
                "tenant_name": "Solo Org",
            }
        res = client.get("/xero/api/connections")
        data = res.get_json()
        assert len(data["connections"]) == 1
        assert data["connections"][0]["is_active"] is True


class TestSwitchConnection:
    """Tests for POST /xero/api/switch-connection."""

    def test_requires_auth(self, client):
        res = client.post(
            "/xero/api/switch-connection",
            json={"tenant_id": "x"},
        )
        assert res.status_code == 401

    def test_missing_tenant_id(self, client):
        _register_and_login(client)
        res = client.post(
            "/xero/api/switch-connection",
            json={},
        )
        assert res.status_code == 400

    def test_tenant_not_found(self, client):
        _register_and_login(client)
        with client.session_transaction() as sess:
            sess["xero_tenants"] = [
                {"tenant_id": "tid_1", "tenant_name": "Org A"},
            ]
        res = client.post(
            "/xero/api/switch-connection",
            json={"tenant_id": "nonexistent"},
        )
        assert res.status_code == 404

    def test_switch_success(self, client):
        """Switching updates the active connection in session."""
        _register_and_login(client)
        with client.session_transaction() as sess:
            sess["xero_connection"] = {
                "access_token": "tok",
                "tenant_id": "tid_1",
                "tenant_name": "Org A",
            }
            sess["xero_tenants"] = [
                {"tenant_id": "tid_1", "tenant_name": "Org A"},
                {"tenant_id": "tid_2", "tenant_name": "Org B"},
            ]
        res = client.post(
            "/xero/api/switch-connection",
            json={"tenant_id": "tid_2"},
        )
        data = res.get_json()
        assert data["success"] is True
        assert data["tenant_name"] == "Org B"

        # Verify session was updated
        status_res = client.get("/api/connection-status")
        status_data = status_res.get_json()
        assert status_data["tenant_name"] == "Org B"
        assert status_data["tenant_id"] == "tid_2"


class TestXeroLogin:
    """Tests for GET /xero/login."""

    def test_requires_auth(self, client):
        res = client.get("/xero/login")
        assert res.status_code == 401

    def test_redirects_to_dashboard(self, client):
        """Placeholder OAuth route redirects to dashboard."""
        _register_and_login(client)
        res = client.get("/xero/login")
        assert res.status_code == 302
        assert "/dashboard" in res.headers["Location"]

    def test_redirects_to_xero_authorize_when_configured(self, client):
        """Configured OAuth values produce an authorize redirect with PKCE."""
        _register_and_login(client)
        client.application.config["XERO_CLIENT_ID"] = "client-123"
        client.application.config["XERO_REDIRECT_URI"] = (
            "https://finql.ai/xero/callback"
        )
        client.application.config["XERO_OAUTH_AUTHORIZE_URL"] = (
            "https://login.xero.com/identity/connect/authorize"
        )
        client.application.config["XERO_SCOPES"] = "openid profile offline_access"

        res = client.get("/xero/login")
        assert res.status_code == 302

        parsed = urlparse(res.headers["Location"])
        assert parsed.scheme == "https"
        assert parsed.netloc == "login.xero.com"
        assert parsed.path == "/identity/connect/authorize"

        qs = parse_qs(parsed.query)
        assert qs["response_type"] == ["code"]
        assert qs["client_id"] == ["client-123"]
        assert qs["redirect_uri"] == ["https://finql.ai/xero/callback"]
        assert qs["scope"] == ["openid profile offline_access"]
        assert qs["code_challenge_method"] == ["S256"]
        assert "state" in qs
        assert "code_challenge" in qs

        with client.session_transaction() as sess:
            assert sess.get("xero_oauth_state")
            assert sess.get("xero_pkce_verifier")


class TestXeroCallback:
    """Tests for GET /xero/callback."""

    def test_requires_auth(self, client):
        res = client.get("/xero/callback")
        assert res.status_code == 401

    def test_invalid_state_redirects(self, client):
        _register_and_login(client)
        with client.session_transaction() as sess:
            sess["xero_oauth_state"] = "expected-state"
            sess["xero_pkce_verifier"] = "verifier"

        res = client.get("/xero/callback?code=abc123&state=wrong-state")
        assert res.status_code == 302
        assert "xero_auth=invalid_state" in res.headers["Location"]

    def test_error_redirects_failed(self, client):
        _register_and_login(client)
        res = client.get("/xero/callback?error=access_denied")
        assert res.status_code == 302
        assert "xero_auth=failed" in res.headers["Location"]

    def test_success_captures_code_and_pkce_verifier(self, client):
        _register_and_login(client)
        with client.session_transaction() as sess:
            sess["xero_oauth_state"] = "state-123"
            sess["xero_pkce_verifier"] = "pkce-verifier-xyz"

        res = client.get("/xero/callback?code=auth-code-1&state=state-123")
        assert res.status_code == 302
        assert "xero_auth=code_received" in res.headers["Location"]

        with client.session_transaction() as sess:
            assert sess.get("xero_oauth_code") == "auth-code-1"
            assert sess.get("xero_oauth_pkce_verifier") == "pkce-verifier-xyz"
            assert "xero_oauth_state" not in sess
