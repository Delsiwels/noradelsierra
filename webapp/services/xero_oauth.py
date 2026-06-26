"""Xero OAuth2 (PKCE) token exchange and refresh.

Exchanges an authorization code for access/refresh tokens, refreshes expired
tokens, and lists tenant connections. Pure HTTP + parsing — persistence lives in
webapp.services.xero_token_store. A confidential-client secret is included only
when XERO_CLIENT_SECRET is configured (PKCE public clients don't need one).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import requests
from flask import current_app

logger = logging.getLogger(__name__)

TOKEN_URL = (
    "https://identity.xero.com/connect/token"  # noqa: S105 (a URL, not a secret)
)
CONNECTIONS_URL = "https://api.xero.com/connections"
_DEFAULT_EXPIRES_IN = 1800  # Xero access tokens last 30 minutes


def _post_token(data: dict) -> dict | None:
    """POST to the Xero token endpoint and return the parsed JSON, or None."""
    token_url = current_app.config.get("XERO_OAUTH_TOKEN_URL", TOKEN_URL)
    client_secret = current_app.config.get("XERO_CLIENT_SECRET")
    if client_secret:
        data = {**data, "client_secret": client_secret}
    try:
        resp = requests.post(
            token_url, data=data, headers={"Accept": "application/json"}, timeout=15
        )
        resp.raise_for_status()
        result: dict = resp.json()
        return result
    except requests.RequestException:
        logger.exception("Xero token request failed")
        return None


def fetch_connections(access_token: str) -> list[dict]:
    """List the tenants an access token is authorised for."""
    try:
        resp = requests.get(
            CONNECTIONS_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return [
            {
                "tenant_id": t.get("tenantId"),
                "tenant_name": t.get("tenantName", "Unknown"),
            }
            for t in resp.json()
        ]
    except requests.RequestException:
        logger.exception("Failed to list Xero connections")
        return []


def _build_connection(tokens: dict, tenants: list[dict]) -> dict:
    expires_in = int(
        tokens.get("expires_in", _DEFAULT_EXPIRES_IN) or _DEFAULT_EXPIRES_IN
    )
    token_expires_at = (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat()
    active = tenants[0] if tenants else {}
    return {
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "token_type": tokens.get("token_type", "Bearer"),
        "id_token": tokens.get("id_token"),
        "token_expires_at": token_expires_at,
        "tenant_id": active.get("tenant_id"),
        "tenant_name": active.get("tenant_name"),
        "tenants": tenants,
    }


def exchange_code(code: str, verifier: str) -> dict | None:
    """Exchange an authorization code (PKCE) for a connection dict, or None."""
    client_id = current_app.config.get("XERO_CLIENT_ID")
    redirect_uri = current_app.config.get("XERO_REDIRECT_URI")
    if not client_id or not redirect_uri:
        logger.warning("Xero OAuth not configured; cannot exchange code")
        return None

    tokens = _post_token(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
        }
    )
    if not tokens or not tokens.get("access_token"):
        return None
    tenants = fetch_connections(tokens["access_token"])
    return _build_connection(tokens, tenants)


def refresh_connection(connection: dict) -> dict | None:
    """Refresh an expired connection using its refresh token, or None."""
    refresh_token = (connection or {}).get("refresh_token")
    client_id = current_app.config.get("XERO_CLIENT_ID")
    if not refresh_token or not client_id:
        return None

    tokens = _post_token(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        }
    )
    if not tokens or not tokens.get("access_token"):
        return None

    tenants = connection.get("tenants") or fetch_connections(tokens["access_token"])
    refreshed = _build_connection(tokens, tenants)
    # Preserve the previously active tenant selection across refresh.
    if connection.get("tenant_id"):
        refreshed["tenant_id"] = connection["tenant_id"]
        refreshed["tenant_name"] = connection.get("tenant_name")
    return refreshed


def is_expired(connection: dict, *, skew_seconds: int = 60) -> bool:
    """True if the connection's access token is expired (within a small skew)."""
    expires_at = (connection or {}).get("token_expires_at")
    if not expires_at:
        return False
    try:
        expiry = datetime.fromisoformat(expires_at)
    except (ValueError, TypeError):
        return False
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    return datetime.now(UTC) >= expiry - timedelta(seconds=skew_seconds)
