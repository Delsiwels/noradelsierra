"""
Xero Connections Blueprint

Manages Xero connection status and org switching via session storage.

Endpoints:
- GET /api/connection-status - Current connection status for the bar
- GET /xero/api/connections - List all available Xero connections
- POST /xero/api/switch-connection - Switch active Xero org
- GET /xero/login - Redirect to Xero OAuth (placeholder)
"""

import logging
import secrets
from base64 import urlsafe_b64encode
from datetime import UTC, datetime
from hashlib import sha256
from urllib.parse import urlencode

from flask import Blueprint, current_app, jsonify, redirect, request, session
from flask_login import current_user, login_required

connections_bp = Blueprint("connections", __name__)

logger = logging.getLogger(__name__)


def _build_pkce_pair() -> tuple[str, str]:
    """Generate PKCE verifier and S256 challenge."""
    verifier = secrets.token_urlsafe(64)[:128]
    challenge = (
        urlsafe_b64encode(sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    return verifier, challenge


def _get_xero_session() -> dict:
    """Read Xero connection data from the Flask session."""
    data: dict = session.get("xero_connection", {})
    return data


def _compute_status(connection: dict) -> str:
    """
    Determine connection health from token expiry.

    Returns one of: healthy, expiring, expired, disconnected.
    """
    if not connection or not connection.get("access_token"):
        return "disconnected"

    expires_at = connection.get("token_expires_at")
    if not expires_at:
        return "healthy"

    try:
        expiry = datetime.fromisoformat(expires_at)
        now = datetime.now(UTC)
        # Ensure expiry is timezone-aware
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        remaining = (expiry - now).total_seconds()
        if remaining <= 0:
            return "expired"
        if remaining < 300:  # less than 5 minutes
            return "expiring"
        return "healthy"
    except (ValueError, TypeError):
        return "healthy"


@connections_bp.route("/api/connection-status", methods=["GET"])
@login_required
def connection_status():
    """
    Return the current Xero connection status for the top bar.

    Response JSON:
        connected: bool
        status: "healthy" | "expiring" | "expired" | "disconnected"
        tenant_name: str | null
        tenant_id: str | null
    """
    conn = _get_xero_session()
    status = _compute_status(conn)

    return jsonify(
        {
            "connected": status in ("healthy", "expiring"),
            "status": status,
            "tenant_name": conn.get("tenant_name"),
            "tenant_id": conn.get("tenant_id"),
        }
    )


@connections_bp.route("/xero/api/connections", methods=["GET"])
@login_required
def list_connections():
    """
    List all Xero tenant connections stored in the session.

    The session stores an array of available tenants from the last
    OAuth handshake.  The active tenant is marked with is_active=True.

    Response JSON:
        connections: list of {tenant_id, tenant_name, is_active}
    """
    conn = _get_xero_session()
    tenants = session.get("xero_tenants", [])
    active_id = conn.get("tenant_id")

    connections = []
    for t in tenants:
        connections.append(
            {
                "tenant_id": t.get("tenant_id", ""),
                "tenant_name": t.get("tenant_name", "Unknown"),
                "is_active": t.get("tenant_id") == active_id,
            }
        )

    # If there are no stored tenants but we have an active connection,
    # return at least that one.
    if not connections and active_id:
        connections.append(
            {
                "tenant_id": active_id,
                "tenant_name": conn.get("tenant_name", "Unknown"),
                "is_active": True,
            }
        )

    return jsonify({"connections": connections})


@connections_bp.route("/xero/api/switch-connection", methods=["POST"])
@login_required
def switch_connection():
    """
    Switch the active Xero tenant.

    Request JSON:
        tenant_id: str - The tenant ID to switch to.

    Updates session so subsequent API calls use the new tenant.
    """
    data = request.get_json(silent=True)
    if not data or not data.get("tenant_id"):
        return jsonify({"error": "tenant_id is required"}), 400

    target_id = str(data["tenant_id"]).strip()
    tenants = session.get("xero_tenants", [])

    # Find the requested tenant
    target = None
    for t in tenants:
        if t.get("tenant_id") == target_id:
            target = t
            break

    if not target:
        return jsonify({"error": "Tenant not found in available connections"}), 404

    # Update the active connection in session
    conn = _get_xero_session()
    conn["tenant_id"] = target["tenant_id"]
    conn["tenant_name"] = target.get("tenant_name", "Unknown")
    session["xero_connection"] = conn
    session.modified = True

    logger.info(
        "User %s switched Xero tenant to %s (%s)",
        current_user.id,
        target.get("tenant_name"),
        target_id,
    )

    return jsonify(
        {
            "success": True,
            "tenant_id": target["tenant_id"],
            "tenant_name": target.get("tenant_name"),
        }
    )


@connections_bp.route("/xero/login", methods=["GET"])
@login_required
def xero_login():
    """
    Initiate Xero OAuth connection flow.

    Redirects to Xero authorize URL when OAuth config is present.
    Falls back to dashboard when credentials are missing.
    """
    client_id = current_app.config.get("XERO_CLIENT_ID")
    redirect_uri = current_app.config.get("XERO_REDIRECT_URI")
    authorize_url = current_app.config.get("XERO_OAUTH_AUTHORIZE_URL")
    scopes = current_app.config.get("XERO_SCOPES", "")

    if not client_id or not redirect_uri or not authorize_url:
        logger.info(
            "Xero OAuth config missing for user %s; redirecting to dashboard",
            current_user.id,
        )
        return redirect("/dashboard")

    state = secrets.token_urlsafe(24)
    verifier, code_challenge = _build_pkce_pair()
    session["xero_oauth_state"] = state
    session["xero_pkce_verifier"] = verifier
    session.modified = True

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    return redirect(f"{authorize_url}?{urlencode(params)}")
