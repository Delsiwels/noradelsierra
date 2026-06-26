"""Tests for Xero OAuth token exchange / refresh (audit #3 follow-up)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from flask import Flask

from webapp.services import xero_oauth


def _app():
    app = Flask(__name__)
    app.config.update(
        XERO_CLIENT_ID="cid",
        XERO_REDIRECT_URI="https://app.example/callback",
        XERO_OAUTH_TOKEN_URL="https://identity.xero.com/connect/token",
    )
    return app


def _resp(payload):
    r = MagicMock()
    r.raise_for_status.return_value = None
    r.json.return_value = payload
    return r


def test_exchange_code_builds_connection():
    app = _app()
    tokens = {
        "access_token": "AT",
        "refresh_token": "RT",
        "expires_in": 1800,
        "token_type": "Bearer",
    }
    conns = [{"tenantId": "t1", "tenantName": "Demo Co"}]
    with (
        app.app_context(),
        patch.object(xero_oauth.requests, "post", return_value=_resp(tokens)) as post,
        patch.object(xero_oauth.requests, "get", return_value=_resp(conns)),
    ):
        conn = xero_oauth.exchange_code("code123", "verifier123")

    assert conn["access_token"] == "AT"
    assert conn["refresh_token"] == "RT"
    assert conn["tenant_id"] == "t1"
    assert conn["tenant_name"] == "Demo Co"
    assert conn["tenants"] == [{"tenant_id": "t1", "tenant_name": "Demo Co"}]
    assert conn["token_expires_at"]  # populated

    sent = post.call_args.kwargs["data"]
    assert sent["grant_type"] == "authorization_code"
    assert sent["code"] == "code123"
    assert sent["code_verifier"] == "verifier123"
    assert sent["client_id"] == "cid"
    assert sent["redirect_uri"] == "https://app.example/callback"


def test_exchange_code_none_on_token_failure():
    app = _app()
    with (
        app.app_context(),
        patch.object(xero_oauth.requests, "post", return_value=_resp({})),
    ):
        assert xero_oauth.exchange_code("c", "v") is None


def test_refresh_connection_uses_refresh_token_and_keeps_tenant():
    app = _app()
    tokens = {"access_token": "AT2", "refresh_token": "RT2", "expires_in": 1800}
    old = {
        "refresh_token": "RT",
        "tenant_id": "t1",
        "tenant_name": "Demo",
        "tenants": [{"tenant_id": "t1", "tenant_name": "Demo"}],
    }
    with (
        app.app_context(),
        patch.object(xero_oauth.requests, "post", return_value=_resp(tokens)) as post,
    ):
        conn = xero_oauth.refresh_connection(old)

    assert conn["access_token"] == "AT2"
    assert conn["tenant_id"] == "t1"  # preserved across refresh
    sent = post.call_args.kwargs["data"]
    assert sent["grant_type"] == "refresh_token"
    assert sent["refresh_token"] == "RT"


def test_is_expired():
    app = _app()
    with app.app_context():
        past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        assert xero_oauth.is_expired({"token_expires_at": past}) is True
        assert xero_oauth.is_expired({"token_expires_at": future}) is False
        assert xero_oauth.is_expired({}) is False
