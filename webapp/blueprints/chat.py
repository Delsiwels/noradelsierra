"""
Chat Blueprint

REST API endpoints for skill-enhanced chat functionality.

Endpoints:
- POST /api/chat - Send message and get skill-enhanced response
- GET /api/chat/skills - Preview which skills would trigger for a message
"""

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__)

# Rate limiter (initialized after app setup)
limiter = None


def init_chat_limiter(app_limiter):
    """Initialize the rate limiter for chat endpoints."""
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
    """
    Get current authenticated user.

    Returns user object or None if not authenticated.
    This is a placeholder - integrate with your auth system.
    """
    from flask import current_app

    # Skip auth check in testing mode
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
    """
    Get current user's primary team ID.

    Returns team_id or None.
    This is a placeholder - integrate with your auth system.
    """
    user = get_current_user()
    if user:
        if hasattr(user, "get_primary_team"):
            team = user.get_primary_team()
            if team:
                return team.id
        elif hasattr(user, "team_id"):
            return user.team_id
    return None


def login_required(f):
    """
    Require login decorator.

    This is a placeholder - replace with your auth system's decorator.
    In testing mode, auth is bypassed.
    """
    from functools import wraps

    from flask import current_app

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip auth check in testing mode
        if current_app.config.get("TESTING"):
            return f(*args, **kwargs)

        try:
            from flask_login import current_user

            if not current_user.is_authenticated:
                return {"error": "Authentication required"}, 401
        except (ImportError, AttributeError):
            # If flask-login is not properly configured, allow request
            pass

        return f(*args, **kwargs)

    return decorated_function


# =============================================================================
# API Routes
# =============================================================================


@chat_bp.route("/api/chat", methods=["POST"])
@rate_limit("60 per hour")
@login_required
def api_chat():
    """
    Send a message and get a skill-enhanced response.

    Request (JSON):
        - message: User message (required)
        - history: Conversation history (optional)
        - industry: Industry context for skill guidelines (optional)
        - base_prompt: Custom base system prompt (optional)

    Response:
        - success: boolean
        - response: AI response content
        - skills_used: List of skill names that were applied
        - usage: Token usage stats
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        user_message = data.get("message", "").strip()
        if not user_message:
            return jsonify({"error": "Message is required"}), 400

        # Validate message length
        if len(user_message) > 32000:
            return (
                jsonify({"error": "Message too long. Maximum 32000 characters."}),
                400,
            )

        # Get conversation history
        history = data.get("history", [])
        if not isinstance(history, list):
            return jsonify({"error": "History must be a list"}), 400

        # Validate history format
        for msg in history:
            if not isinstance(msg, dict):
                return jsonify({"error": "History entries must be objects"}), 400
            if "role" not in msg or "content" not in msg:
                return (
                    jsonify(
                        {"error": "History entries must have 'role' and 'content' keys"}
                    ),
                    400,
                )
            if msg["role"] not in ("user", "assistant"):
                return (
                    jsonify({"error": "History role must be 'user' or 'assistant'"}),
                    400,
                )

        # Get optional parameters
        industry = data.get("industry")
        base_prompt = data.get("base_prompt")

        # Get user context
        user = get_current_user()
        user_id = user.id if user else None
        team_id = get_user_team_id()

        # Get chat service
        from webapp.ai import get_chat_service

        service = get_chat_service()

        if service is None:
            return (
                jsonify(
                    {
                        "error": "Chat service not available. "
                        "AI provider may not be configured."
                    }
                ),
                503,
            )

        # Send message
        response = service.send_message(
            user_message=user_message,
            conversation_history=history,
            user_id=user_id,
            team_id=team_id,
            industry=industry,
            base_prompt=base_prompt,
        )

        return jsonify(
            {
                "success": True,
                "response": response.content,
                "skills_used": response.skills_used,
                "model": response.model,
                "usage": response.usage,
            }
        )

    except ValueError as e:
        logger.error(f"Chat error: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception(f"Unexpected chat error: {e}")
        return jsonify({"error": "An error occurred processing your request"}), 500


@chat_bp.route("/api/chat/skills", methods=["GET"])
@rate_limit("100 per hour")
@login_required
def api_preview_skills():
    """
    Preview which skills would trigger for a given message.

    Query params:
        - message: Message to check (required)

    Response:
        - success: boolean
        - skills: List of matching skills with name, description, trigger, confidence
    """
    try:
        message = request.args.get("message", "").strip()
        if not message:
            return jsonify({"error": "Message query parameter is required"}), 400

        # Validate message length
        if len(message) > 32000:
            return (
                jsonify({"error": "Message too long. Maximum 32000 characters."}),
                400,
            )

        # Get user context
        user = get_current_user()
        user_id = user.id if user else None
        team_id = get_user_team_id()

        # Get chat service
        from webapp.ai import get_chat_service

        service = get_chat_service()

        if service is None:
            # Even without AI, we can still preview skills
            from webapp.skills import get_injector

            injector = get_injector()
            matches = injector.detect_skill_triggers(message, user_id, team_id)
            skills = [
                {
                    "name": m.skill.name,
                    "description": m.skill.description,
                    "trigger": m.trigger,
                    "confidence": m.confidence,
                    "source": m.skill.source,
                }
                for m in matches
            ]
        else:
            skills = service.preview_skills(message, user_id, team_id)

        return jsonify(
            {
                "success": True,
                "skills": skills,
                "message": message,
            }
        )

    except Exception as e:
        logger.exception(f"Error previewing skills: {e}")
        return jsonify({"error": "Failed to preview skills"}), 500
