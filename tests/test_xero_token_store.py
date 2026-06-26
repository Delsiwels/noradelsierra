"""Tests for server-side encrypted Xero token storage (audit #3)."""

from webapp.app import create_app
from webapp.config import TestingConfig


class _EncryptedConfig(TestingConfig):
    TOKEN_ENCRYPTION_KEY = "test-token-encryption-key"  # noqa: S105 (test value)


def test_save_load_clear_round_trip():
    app = create_app(_EncryptedConfig)
    with app.app_context():
        from webapp.services import xero_token_store as store

        assert store.is_available() is True
        conn = {
            "access_token": "xero-access-tok",
            "refresh_token": "xero-refresh-tok",
            "tenant_id": "tenant-1",
            "tenant_name": "Demo Co",
        }
        assert store.save_connection("user-1", conn) is True
        assert store.load_connection("user-1") == conn

        # Overwrite (upsert) works.
        conn2 = {**conn, "tenant_id": "tenant-2"}
        assert store.save_connection("user-1", conn2) is True
        assert store.load_connection("user-1")["tenant_id"] == "tenant-2"

        store.clear_connection("user-1")
        assert store.load_connection("user-1") is None


def test_token_not_stored_in_plaintext():
    app = create_app(_EncryptedConfig)
    with app.app_context():
        from webapp.models import XeroToken
        from webapp.services import xero_token_store as store

        store.save_connection("user-2", {"access_token": "SUPERSECRET"})
        row = XeroToken.query.filter_by(user_id="user-2").first()
        assert "SUPERSECRET" not in row.encrypted_data


def test_noop_without_key():
    app = create_app(TestingConfig)  # no TOKEN_ENCRYPTION_KEY
    with app.app_context():
        from webapp.services import xero_token_store as store

        assert store.is_available() is False
        assert store.save_connection("user-3", {"access_token": "x"}) is False
        assert store.load_connection("user-3") is None
