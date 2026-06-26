"""Shared helpers for blueprint route modules."""

from functools import wraps

from flask import current_app, jsonify, session


def get_current_user():
    """Get the current authenticated user, or None (None in testing mode)."""
    if current_app.config.get("TESTING"):
        return None
    try:
        from flask_login import current_user

        if current_user.is_authenticated:
            return current_user
    except (ImportError, AttributeError):
        pass
    return None


def get_user_team_id():
    """Get the current user's primary team ID, or None."""
    user = get_current_user()
    if user and hasattr(user, "team_id"):
        return user.team_id
    return None


def login_required(f):
    """Require login decorator. Bypassed in testing mode."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_app.config.get("TESTING"):
            return f(*args, **kwargs)
        try:
            from flask_login import current_user

            if not current_user.is_authenticated:
                return jsonify({"error": "Authentication required"}), 401
        except (ImportError, AttributeError):
            pass
        return f(*args, **kwargs)

    return decorated_function


def get_xero_credentials() -> tuple[str | None, str | None]:
    """Get the Xero access token and tenant ID for the current user.

    Prefers the encrypted server-side token store; falls back to the session
    (and legacy flat session keys) when the store is empty or unavailable, so
    existing connections keep working during migration.
    """
    from flask_login import current_user

    from webapp.services import xero_token_store

    user_id = getattr(current_user, "id", None)
    conn = xero_token_store.load_active_connection(user_id) or session.get(
        "xero_connection", {}
    )
    access_token = conn.get("access_token") or session.get("xero_access_token")
    tenant_id = conn.get("tenant_id") or session.get("xero_tenant_id")
    return access_token, tenant_id
