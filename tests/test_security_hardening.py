"""Regression tests for security-hardening fixes (see security-audit-ledger)."""


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
