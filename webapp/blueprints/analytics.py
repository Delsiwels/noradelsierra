"""
Analytics Blueprint

REST API endpoints for skill usage analytics.

Endpoints:
- GET /api/analytics/skills - Skill usage statistics
- GET /api/analytics/skills/user/<id> - Per-user skill stats
- GET /api/analytics/skills/<name> - Stats for a specific skill
- GET /api/analytics/summary - Overall usage summary
"""

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

analytics_bp = Blueprint("analytics", __name__)

# Rate limiter (initialized after app setup)
limiter = None


def init_analytics_limiter(app_limiter):
    """Initialize the rate limiter for analytics endpoints."""
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


@analytics_bp.route("/api/analytics/skills", methods=["GET"])
@rate_limit("100 per hour")
@login_required
def api_get_skill_analytics():
    """
    Get skill usage statistics.

    Query params:
        - period: Number of days to look back (default: 30)
        - limit: Max number of skills to return (default: 10)

    Response:
        - success: boolean
        - top_skills: List of top skills with usage stats
        - period_days: Period covered
    """
    try:
        from webapp.skills.analytics_service import get_analytics_service

        service = get_analytics_service()

        period_days = int(request.args.get("period", 30))
        limit = min(int(request.args.get("limit", 10)), 50)

        top_skills = service.get_top_skills(period_days=period_days, limit=limit)

        return jsonify(
            {
                "success": True,
                "top_skills": top_skills,
                "period_days": period_days,
            }
        )

    except Exception as e:
        logger.exception(f"Error getting skill analytics: {e}")
        return jsonify({"error": "Failed to get skill analytics"}), 500


@analytics_bp.route("/api/analytics/skills/user/<user_id>", methods=["GET"])
@rate_limit("100 per hour")
@login_required
def api_get_user_skill_stats(user_id):
    """
    Get skill usage statistics for a specific user.

    Path params:
        - user_id: User ID

    Response:
        - success: boolean
        - stats: User skill statistics
    """
    try:
        from flask import current_app

        from webapp.skills.analytics_service import get_analytics_service

        # Verify user can access this data (own data or admin)
        user = get_current_user()
        if user and user.id != user_id:
            # Check if admin (placeholder - implement your own admin check)
            if not getattr(user, "is_admin", False):
                return jsonify({"error": "Access denied"}), 403

        # In testing mode, allow access
        if user is None and not current_app.config.get("TESTING"):
            return jsonify({"error": "Authentication required"}), 401

        service = get_analytics_service()
        stats = service.get_user_stats(user_id)

        return jsonify(
            {
                "success": True,
                "stats": stats,
            }
        )

    except Exception as e:
        logger.exception(f"Error getting user skill stats: {e}")
        return jsonify({"error": "Failed to get user skill stats"}), 500


@analytics_bp.route("/api/analytics/skills/<skill_name>", methods=["GET"])
@rate_limit("100 per hour")
@login_required
def api_get_skill_detail_stats(skill_name):
    """
    Get detailed statistics for a specific skill.

    Path params:
        - skill_name: Name of the skill

    Response:
        - success: boolean
        - stats: Skill statistics
    """
    try:
        from webapp.skills.analytics_service import get_analytics_service

        service = get_analytics_service()
        stats = service.get_skill_stats(skill_name)

        return jsonify(
            {
                "success": True,
                "stats": stats,
            }
        )

    except Exception as e:
        logger.exception(f"Error getting skill detail stats: {e}")
        return jsonify({"error": "Failed to get skill stats"}), 500


@analytics_bp.route("/api/analytics/summary", methods=["GET"])
@rate_limit("100 per hour")
@login_required
def api_get_analytics_summary():
    """
    Get overall skill usage summary.

    Query params:
        - period: Number of days to look back (default: 30)

    Response:
        - success: boolean
        - summary: Overall usage summary
    """
    try:
        from webapp.skills.analytics_service import get_analytics_service

        service = get_analytics_service()

        period_days = int(request.args.get("period", 30))
        summary = service.get_summary(period_days=period_days)

        return jsonify(
            {
                "success": True,
                "summary": summary,
            }
        )

    except Exception as e:
        logger.exception(f"Error getting analytics summary: {e}")
        return jsonify({"error": "Failed to get analytics summary"}), 500
