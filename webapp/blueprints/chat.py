"""
Chat Blueprint

REST API endpoints for skill-enhanced chat functionality.

Endpoints:
- POST /api/chat - Send message and get skill-enhanced response
- POST /api/chat/stream - Send message with SSE streaming response
- GET /api/chat/skills - Preview which skills would trigger for a message
- GET /api/conversations - List user's conversations
- GET /api/conversations/<id> - Get conversation with messages
- DELETE /api/conversations/<id> - Delete conversation
"""

import json
import logging

from flask import Blueprint, Response, jsonify, request

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


def validate_chat_request(data):
    """Validate common chat request parameters. Returns (error_response, status) or (None, None)."""
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Message is required"}), 400

    if len(user_message) > 32000:
        return (
            jsonify({"error": "Message too long. Maximum 32000 characters."}),
            400,
        )

    history = data.get("history", [])
    if not isinstance(history, list):
        return jsonify({"error": "History must be a list"}), 400

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

    return None, None


def _parse_int_query_arg(
    name: str,
    *,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Parse and validate integer query arguments."""
    raw = request.args.get(name, None)
    if raw in (None, ""):
        value = default
    else:
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be an integer") from exc

    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None:
        value = min(value, maximum)
    return value


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
        - persist: Whether to persist the conversation (default: false)
        - conversation_id: Existing conversation ID to continue (optional)

    Response:
        - success: boolean
        - response: AI response content
        - skills_used: List of skill names that were applied
        - model: Model used
        - usage: Token usage stats
        - conversation_id: Conversation ID (if persisted)
    """
    try:
        data = request.get_json(silent=True)

        # Validate request
        error_response, status = validate_chat_request(data)
        if error_response:
            return error_response, status

        user_message = data.get("message", "").strip()
        history = data.get("history", [])
        industry = data.get("industry")
        base_prompt = data.get("base_prompt")
        persist = data.get("persist", False)
        conversation_id = data.get("conversation_id")

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
            persist=persist,
            conversation_id=conversation_id,
        )

        result = {
            "success": True,
            "response": response.content,
            "skills_used": response.skills_used,
            "model": response.model,
            "usage": response.usage,
        }

        if response.conversation_id:
            result["conversation_id"] = response.conversation_id

        return jsonify(result)

    except ValueError as e:
        logger.error(f"Chat error: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        # Check for token limit exceeded
        if (
            "TokenLimitExceededError" in type(e).__name__
            or "token limit" in str(e).lower()
        ):
            return jsonify({"error": str(e)}), 429
        logger.exception(f"Unexpected chat error: {e}")
        return jsonify({"error": "An error occurred processing your request"}), 500


@chat_bp.route("/api/chat/stream", methods=["POST"])
@rate_limit("60 per hour")
@login_required
def api_chat_stream():
    """
    Send a message and get a streaming SSE response.

    Request (JSON):
        - message: User message (required)
        - history: Conversation history (optional)
        - industry: Industry context for skill guidelines (optional)
        - base_prompt: Custom base system prompt (optional)
        - persist: Whether to persist the conversation (default: false)
        - conversation_id: Existing conversation ID to continue (optional)

    Response (SSE):
        event: chunk
        data: {"content": "partial...", "done": false}

        event: chunk
        data: {"content": "", "done": true, "skills_used": [...], "usage": {...}}
    """
    try:
        data = request.get_json(silent=True)

        # Validate request
        error_response, status = validate_chat_request(data)
        if error_response:
            return error_response, status

        user_message = data.get("message", "").strip()
        history = data.get("history", [])
        industry = data.get("industry")
        base_prompt = data.get("base_prompt")
        persist = data.get("persist", False)
        conversation_id = data.get("conversation_id")

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

        def generate():
            """Generate SSE events from stream."""
            try:
                for chunk in service.send_message_stream(
                    user_message=user_message,
                    conversation_history=history,
                    user_id=user_id,
                    team_id=team_id,
                    industry=industry,
                    base_prompt=base_prompt,
                    persist=persist,
                    conversation_id=conversation_id,
                ):
                    event_data = {
                        "content": chunk.content,
                        "done": chunk.done,
                    }

                    if chunk.done:
                        event_data["skills_used"] = chunk.skills_used
                        event_data["usage"] = chunk.usage
                        event_data["model"] = chunk.model
                        if chunk.error:
                            event_data["error"] = chunk.error

                    yield f"event: chunk\ndata: {json.dumps(event_data)}\n\n"

            except Exception as e:
                error_data = {
                    "content": "",
                    "done": True,
                    "error": str(e),
                }
                yield f"event: chunk\ndata: {json.dumps(error_data)}\n\n"

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except ValueError as e:
        logger.error(f"Chat stream error: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        if (
            "TokenLimitExceededError" in type(e).__name__
            or "token limit" in str(e).lower()
        ):
            return jsonify({"error": str(e)}), 429
        logger.exception(f"Unexpected chat stream error: {e}")
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


# =============================================================================
# Conversation Routes
# =============================================================================


@chat_bp.route("/api/conversations", methods=["GET"])
@rate_limit("100 per hour")
@login_required
def api_list_conversations():
    """
    List user's conversations.

    Query params:
        - limit: Max number of conversations (default: 20, max: 100)
        - offset: Pagination offset (default: 0)

    Response:
        - success: boolean
        - conversations: List of conversation summaries
        - total: Total number of conversations
    """
    try:
        from webapp.models import Conversation

        # Parse pagination params first so invalid input is rejected
        # consistently in both testing and authenticated runtime.
        limit = _parse_int_query_arg("limit", default=20, minimum=1, maximum=100)
        offset = _parse_int_query_arg("offset", default=0, minimum=0)

        user = get_current_user()
        user_id = user.id if user else None

        # In testing mode, return empty list if no user
        if user_id is None:
            from flask import current_app

            if current_app.config.get("TESTING"):
                return jsonify(
                    {
                        "success": True,
                        "conversations": [],
                        "total": 0,
                    }
                )
            return jsonify({"error": "Authentication required"}), 401

        # Query conversations
        query = Conversation.query.filter_by(user_id=user_id).order_by(
            Conversation.updated_at.desc()
        )

        total = query.count()
        conversations = query.offset(offset).limit(limit).all()

        return jsonify(
            {
                "success": True,
                "conversations": [c.to_dict() for c in conversations],
                "total": total,
            }
        )

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception(f"Error listing conversations: {e}")
        return jsonify({"error": "Failed to list conversations"}), 500


@chat_bp.route("/api/conversations/<conversation_id>", methods=["GET"])
@rate_limit("100 per hour")
@login_required
def api_get_conversation(conversation_id):
    """
    Get a conversation with its messages.

    Path params:
        - conversation_id: Conversation ID

    Response:
        - success: boolean
        - conversation: Conversation with messages
    """
    try:
        from webapp.models import Conversation, db

        user = get_current_user()
        user_id = user.id if user else None

        # In testing mode, allow access without user
        from flask import current_app

        if user_id is None and not current_app.config.get("TESTING"):
            return jsonify({"error": "Authentication required"}), 401

        conversation = db.session.get(Conversation, conversation_id)

        if not conversation:
            return jsonify({"error": "Conversation not found"}), 404

        # Check ownership (skip in testing mode)
        if user_id and conversation.user_id != user_id:
            return jsonify({"error": "Access denied"}), 403

        return jsonify(
            {
                "success": True,
                "conversation": conversation.to_dict(include_messages=True),
            }
        )

    except Exception as e:
        logger.exception(f"Error getting conversation: {e}")
        return jsonify({"error": "Failed to get conversation"}), 500


@chat_bp.route("/api/conversations/<conversation_id>", methods=["DELETE"])
@rate_limit("30 per hour")
@login_required
def api_delete_conversation(conversation_id):
    """
    Delete a conversation.

    Path params:
        - conversation_id: Conversation ID

    Response:
        - success: boolean
    """
    try:
        from webapp.models import Conversation, db

        user = get_current_user()
        user_id = user.id if user else None

        # In testing mode, allow deletion without user
        from flask import current_app

        if user_id is None and not current_app.config.get("TESTING"):
            return jsonify({"error": "Authentication required"}), 401

        conversation = db.session.get(Conversation, conversation_id)

        if not conversation:
            return jsonify({"error": "Conversation not found"}), 404

        # Check ownership (skip in testing mode)
        if user_id and conversation.user_id != user_id:
            return jsonify({"error": "Access denied"}), 403

        db.session.delete(conversation)
        db.session.commit()

        return jsonify({"success": True})

    except Exception as e:
        logger.exception(f"Error deleting conversation: {e}")
        return jsonify({"error": "Failed to delete conversation"}), 500
