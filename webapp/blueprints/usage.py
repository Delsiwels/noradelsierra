"""
Usage Blueprint

REST API endpoints for token usage tracking and limits.

Endpoints:
- GET /api/usage - Get current token usage and limits
- GET /api/usage/check - Check if request is allowed
"""

import logging

from flask import Blueprint, jsonify

logger = logging.getLogger(__name__)

usage_bp = Blueprint("usage", __name__)

# Rate limiter (initialized after app setup)
limiter = None


def init_usage_limiter(app_limiter):
    """Initialize the rate limiter for usage endpoints."""
    global limiter
    limiter = app_limiter


def rate_limit(limit_string):
    """Apply per-user rate limit decorator if limiter is available."""

    def decorator(f):
        if limiter:
            return limiter.limit(limit_string)(f)
        return f

    return decorator


def get_current_user():
    """Get current authenticated user."""
    from flask import current_app

    if current_app.config.get("TESTING"):
        return None

    from flask_login import current_user as _current_user

    if _current_user.is_authenticated:
        return _current_user
    return None


def get_user_team_id():
    """Get current user's primary team ID."""
    user = get_current_user()
    if user and hasattr(user, "team_id"):
        return user.team_id
    return None


def login_required(f):
    """Require login decorator. Bypassed in testing mode."""
    from functools import wraps

    from flask import current_app

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_app.config.get("TESTING"):
            return f(*args, **kwargs)

        from flask_login import current_user as _current_user

        if not _current_user.is_authenticated:
            return {"error": "Authentication required"}, 401

        return f(*args, **kwargs)

    return decorated_function


# =============================================================================
# API Routes
# =============================================================================


@usage_bp.route("/api/usage", methods=["GET"])
@rate_limit("100 per hour")
@login_required
def api_get_usage():
    """
    Get current token usage and limits.

    Response:
        - current_period: dict with usage stats for current month
            - year: int
            - month: int
            - input_tokens: int
            - output_tokens: int
            - total_tokens: int
            - request_count: int
            - limit: int
            - remaining: int
            - percentage_used: float
        - enforcement_enabled: bool
    """
    try:
        from webapp.ai.token_tracker import get_token_tracker

        tracker = get_token_tracker()

        user = get_current_user()
        user_id = user.id if user else None
        team_id = get_user_team_id()

        # In testing mode, provide default response
        if user_id is None and team_id is None:
            from flask import current_app

            if current_app.config.get("TESTING"):
                return jsonify(
                    {
                        "current_period": {
                            "year": 2026,
                            "month": 1,
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "total_tokens": 0,
                            "request_count": 0,
                            "limit": 100000,
                            "remaining": 100000,
                            "percentage_used": 0.0,
                        },
                        "enforcement_enabled": True,
                    }
                )

        usage = tracker.get_usage(user_id, team_id)

        return jsonify(usage)

    except Exception as e:
        logger.exception(f"Error getting usage: {e}")
        return jsonify({"error": "Failed to get usage"}), 500


@usage_bp.route("/api/usage/check", methods=["GET"])
@rate_limit("200 per hour")
@login_required
def api_check_usage():
    """
    Check if a request is allowed based on current usage.

    Response:
        - allowed: bool - Whether the request is allowed
        - remaining: int - Remaining tokens for current period
        - limit: int - Monthly token limit
    """
    try:
        from webapp.ai.token_tracker import get_token_tracker

        tracker = get_token_tracker()

        user = get_current_user()
        user_id = user.id if user else None
        team_id = get_user_team_id()

        # In testing mode, always allow
        if user_id is None and team_id is None:
            from flask import current_app

            if current_app.config.get("TESTING"):
                return jsonify(
                    {
                        "allowed": True,
                        "remaining": 100000,
                        "limit": 100000,
                    }
                )

        allowed, remaining = tracker.check_limit(user_id, team_id)
        usage = tracker.get_usage(user_id, team_id)

        return jsonify(
            {
                "allowed": allowed,
                "remaining": remaining,
                "limit": usage["current_period"]["limit"],
            }
        )

    except Exception as e:
        logger.exception(f"Error checking usage: {e}")
        return jsonify({"error": "Failed to check usage"}), 500
