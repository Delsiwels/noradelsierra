"""Regression tests for the production SECRET_KEY guard (audit item #2)."""

import pytest
from flask import Flask

from webapp.services.startup_checks import require_secure_secret_key

_DEV_DEFAULT = "dev-key-change-in-production"  # noqa: S105 (the sentinel under test)
_PROD_ENV_VARS = (
    "FLASK_ENV",
    "APP_ENV",
    "RAILWAY_ENVIRONMENT",
    "RAILWAY_ENVIRONMENT_NAME",
    "RAILWAY_PROJECT_ID",
)


def _app(secret_key):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = secret_key
    return app


def test_blocks_default_key_in_production(monkeypatch):
    for var in _PROD_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    with pytest.raises(RuntimeError):
        require_secure_secret_key(_app(_DEV_DEFAULT))


def test_allows_real_key_in_production(monkeypatch):
    for var in _PROD_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    # A correctly configured prod must NOT be blocked.
    require_secure_secret_key(_app("a-strong-random-secret-value-0123456789"))


def test_noop_outside_production(monkeypatch):
    for var in _PROD_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    # Dev/test context: default key is only a warning, never a hard failure.
    require_secure_secret_key(_app(_DEV_DEFAULT))
