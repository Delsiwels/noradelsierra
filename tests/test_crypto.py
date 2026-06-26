"""Tests for the at-rest token encryption helper (audit #3)."""

from flask import Flask

from webapp.services import crypto


def _app(key):
    app = Flask(__name__)
    if key is not None:
        app.config["TOKEN_ENCRYPTION_KEY"] = key
    return app


def test_round_trip_with_arbitrary_key():
    app = _app("any-arbitrary-secret-string")
    with app.app_context():
        assert crypto.encryption_available() is True
        token = crypto.encrypt("xero-access-token-value")
        assert token is not None
        assert token != "xero-access-token-value"  # actually encrypted
        assert crypto.decrypt(token) == "xero-access-token-value"


def test_round_trip_with_real_fernet_key():
    from cryptography.fernet import Fernet

    app = _app(Fernet.generate_key().decode())
    with app.app_context():
        token = crypto.encrypt("secret")
        assert crypto.decrypt(token) == "secret"


def test_unavailable_without_key():
    app = _app(None)
    with app.app_context():
        assert crypto.encryption_available() is False
        assert crypto.encrypt("secret") is None
        assert crypto.decrypt("anything") is None


def test_decrypt_bad_value_returns_none():
    app = _app("a-key")
    with app.app_context():
        assert crypto.decrypt("not-a-valid-token") is None
