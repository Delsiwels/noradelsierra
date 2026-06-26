"""Regression tests for security-hardening fixes (see security-audit-ledger)."""

import pytest


@pytest.fixture
def client():
    from webapp.app import create_app
    from webapp.config import TestingConfig

    app = create_app(TestingConfig)
    return app.test_client()


class TestSecurityHeaders:
    """F4: baseline security response headers on every response."""

    def test_headers_present_on_health(self, client):
        resp = client.get("/health")
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("Referrer-Policy") == "no-referrer"
        assert "frame-ancestors 'none'" in resp.headers.get(
            "Content-Security-Policy", ""
        )
        assert "max-age=" in resp.headers.get("Strict-Transport-Security", "")


class TestSessionCookieSecure:
    """F5: session cookie must be Secure in production, not forced elsewhere."""

    def test_production_forces_secure_cookie(self):
        from webapp.config import ProductionConfig

        assert ProductionConfig.SESSION_COOKIE_SECURE is True

    def test_base_and_testing_do_not_force_secure(self):
        # Local HTTP and the test client rely on Secure NOT being forced here.
        from webapp.config import Config, TestingConfig

        assert getattr(Config, "SESSION_COOKIE_SECURE", False) is False
        assert getattr(TestingConfig, "SESSION_COOKIE_SECURE", False) is False
