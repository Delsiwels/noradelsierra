"""
Skills Blueprint

Provides routes for managing custom skills:
- GET /skills - List page (private + team + public)
- GET /skills/<id> - Skill detail page
- POST /api/skills/upload - Upload SKILL.md file
- POST /api/skills/create - Create via form
- PUT /api/skills/<id> - Update skill
- DELETE /api/skills/<id> - Delete skill
- POST /api/skills/<id>/share - Promote to team
"""

import logging
import re
import uuid

from flask import Blueprint, jsonify, render_template, request

# Support both local and deployed import paths
try:
    from webapp.skills.custom_skill_service import (
        DuplicateSkillError,
        PermissionDeniedError,
        SkillNotFoundError,
        ValidationError,
        get_custom_skill_service,
    )
    from webapp.skills.skill_registry import get_registry
except ImportError:
    from skills.custom_skill_service import (  # type: ignore[no-redef]
        DuplicateSkillError,
        PermissionDeniedError,
        SkillNotFoundError,
        ValidationError,
        get_custom_skill_service,
    )
    from skills.skill_registry import get_registry  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

skills_bp = Blueprint("skills", __name__, url_prefix="/skills")

# Rate limiter (initialized after app setup)
limiter = None


def init_skills_limiter(app_limiter):
    """Initialize the rate limiter for skills endpoints."""
    global limiter
    limiter = app_limiter


def rate_limit(limit_string):
    """Apply per-user rate limit decorator if limiter is available."""

    def decorator(f):
        if limiter:
            return limiter.limit(limit_string)(f)
        return f

    return decorator


# Maximum file size for SKILL.md (100KB)
MAX_SKILL_FILE_SIZE = 100 * 1024

# Filename validation pattern
SAFE_FILENAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*\.md$")


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


def validate_uuid(value: str) -> bool:
    """Validate UUID format."""
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


# =============================================================================
# Page Routes
# =============================================================================


@skills_bp.route("/")
@login_required
def skills_list_page():
    """Render the skills list page."""
    user = get_current_user()
    return render_template("skills/index.html", user=user)


@skills_bp.route("/<skill_id>")
@login_required
def skill_detail_page(skill_id: str):
    """Render the skill detail page."""
    if not validate_uuid(skill_id):
        return render_template("skills/index.html", error="Invalid skill ID"), 400

    user = get_current_user()
    service = get_custom_skill_service()
    skill = service.get_skill(skill_id)

    if not skill:
        return render_template("skills/index.html", error="Skill not found"), 404

    return render_template("skills/detail.html", skill=skill, user=user)


@skills_bp.route("/create")
@login_required
def skill_create_page():
    """Render the skill creation page."""
    user = get_current_user()
    return render_template("skills/create.html", user=user)


@skills_bp.route("/<skill_id>/edit")
@login_required
def skill_edit_page(skill_id: str):
    """Render the skill edit page."""
    if not validate_uuid(skill_id):
        return render_template("skills/index.html", error="Invalid skill ID"), 400

    user = get_current_user()
    service = get_custom_skill_service()
    skill = service.get_skill(skill_id)

    if not skill:
        return render_template("skills/index.html", error="Skill not found"), 404

    # Get content from R2
    content = service.get_skill_content(skill_id)

    return render_template("skills/edit.html", skill=skill, content=content, user=user)


# =============================================================================
# API Routes
# =============================================================================


@skills_bp.route("/api/skills", methods=["GET"])
@rate_limit("100 per hour")
@login_required
def api_list_skills():
    """
    List all skills for the current user.

    Returns skills grouped by source: private, shared, public.
    """
    try:
        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401

        user_id = user.id
        team_id = get_user_team_id()

        registry = get_registry()
        all_skills = registry.discover_all_skills(user_id, team_id)

        # Convert to serializable format
        result = {
            "private": [s.to_dict() for s in all_skills["private"]],
            "shared": [s.to_dict() for s in all_skills["shared"]],
            "public": [s.to_dict() for s in all_skills["public"]],
        }

        return jsonify({"success": True, "skills": result})

    except Exception as e:
        logger.error(f"Error listing skills: {e}")
        return jsonify({"error": "Failed to list skills"}), 500


@skills_bp.route("/api/skills/<skill_id>", methods=["GET"])
@rate_limit("100 per hour")
@login_required
def api_get_skill(skill_id: str):
    """
    Get a custom skill by ID, including content.
    """
    try:
        if not validate_uuid(skill_id):
            return jsonify({"error": "Invalid skill ID"}), 400

        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401

        service = get_custom_skill_service()
        skill = service.get_skill(skill_id)

        if not skill:
            return jsonify({"error": "Skill not found"}), 404

        # Permission check for private skills
        if skill.scope == "private" and skill.user_id != user.id:
            return jsonify({"error": "Access denied"}), 403

        # Get content
        content = service.get_skill_content(skill_id)

        result = skill.to_dict()
        result["content"] = content

        return jsonify({"success": True, "skill": result})

    except Exception as e:
        logger.error(f"Error getting skill {skill_id}: {e}")
        return jsonify({"error": "Failed to get skill"}), 500


@skills_bp.route("/api/skills/upload", methods=["POST"])
@rate_limit("20 per hour")
@login_required
def api_upload_skill():
    """
    Upload a SKILL.md file to create a new skill.

    Request:
        - file: SKILL.md file (multipart/form-data)
        - scope: 'private' or 'shared' (default: 'private')
    """
    try:
        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401

        # Check for file
        if "file" not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        file = request.files["file"]
        if not file.filename:
            return jsonify({"error": "No file selected"}), 400

        # Validate filename
        if not file.filename.lower().endswith(".md"):
            return jsonify({"error": "File must be a Markdown file (.md)"}), 400

        # Read content
        content = file.read()

        # Check size
        if len(content) > MAX_SKILL_FILE_SIZE:
            return (
                jsonify(
                    {
                        "error": f"File too large. Maximum size is {MAX_SKILL_FILE_SIZE // 1024}KB"
                    }
                ),
                400,
            )

        # Decode content
        try:
            content_str = content.decode("utf-8")
        except UnicodeDecodeError:
            return jsonify({"error": "File must be UTF-8 encoded"}), 400

        # Get scope
        scope = request.form.get("scope", "private")
        if scope not in ("private", "shared"):
            return (
                jsonify({"error": "Invalid scope. Must be 'private' or 'shared'"}),
                400,
            )

        # Get ownership IDs
        user_id = user.id
        team_id = get_user_team_id() if scope == "shared" else None

        if scope == "shared" and not team_id:
            return jsonify({"error": "No team found. Cannot create shared skill."}), 400

        # Create skill
        service = get_custom_skill_service()
        skill = service.create_skill(
            content=content_str,
            scope=scope,
            user_id=user_id if scope == "private" else None,
            team_id=team_id if scope == "shared" else None,
            created_by=user_id,
        )

        return jsonify(
            {
                "success": True,
                "skill": skill.to_dict(),
                "message": f"Skill '{skill.name}' created successfully",
            }
        )

    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    except DuplicateSkillError as e:
        return jsonify({"error": str(e)}), 409
    except Exception as e:
        logger.error(f"Error uploading skill: {e}")
        return jsonify({"error": "Failed to create skill"}), 500


@skills_bp.route("/api/skills/create", methods=["POST"])
@rate_limit("20 per hour")
@login_required
def api_create_skill():
    """
    Create a skill via form data.

    Request (JSON):
        - content: SKILL.md content
        - scope: 'private' or 'shared' (default: 'private')
    """
    try:
        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401

        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        content = data.get("content", "").strip()
        if not content:
            return jsonify({"error": "Content is required"}), 400

        # Check size
        if len(content.encode("utf-8")) > MAX_SKILL_FILE_SIZE:
            return (
                jsonify(
                    {
                        "error": f"Content too large. Maximum size is {MAX_SKILL_FILE_SIZE // 1024}KB"
                    }
                ),
                400,
            )

        # Get scope
        scope = data.get("scope", "private")
        if scope not in ("private", "shared"):
            return (
                jsonify({"error": "Invalid scope. Must be 'private' or 'shared'"}),
                400,
            )

        # Get ownership IDs
        user_id = user.id
        team_id = get_user_team_id() if scope == "shared" else None

        if scope == "shared" and not team_id:
            return jsonify({"error": "No team found. Cannot create shared skill."}), 400

        # Create skill
        service = get_custom_skill_service()
        skill = service.create_skill(
            content=content,
            scope=scope,
            user_id=user_id if scope == "private" else None,
            team_id=team_id if scope == "shared" else None,
            created_by=user_id,
        )

        return jsonify(
            {
                "success": True,
                "skill": skill.to_dict(),
                "message": f"Skill '{skill.name}' created successfully",
            }
        )

    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    except DuplicateSkillError as e:
        return jsonify({"error": str(e)}), 409
    except Exception as e:
        logger.error(f"Error creating skill: {e}")
        return jsonify({"error": "Failed to create skill"}), 500


@skills_bp.route("/api/skills/<skill_id>", methods=["PUT"])
@rate_limit("30 per hour")
@login_required
def api_update_skill(skill_id: str):
    """
    Update an existing skill.

    Request (JSON):
        - content: New SKILL.md content
    """
    try:
        if not validate_uuid(skill_id):
            return jsonify({"error": "Invalid skill ID"}), 400

        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401

        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        content = data.get("content", "").strip()
        if not content:
            return jsonify({"error": "Content is required"}), 400

        # Check size
        if len(content.encode("utf-8")) > MAX_SKILL_FILE_SIZE:
            return (
                jsonify(
                    {
                        "error": f"Content too large. Maximum size is {MAX_SKILL_FILE_SIZE // 1024}KB"
                    }
                ),
                400,
            )

        # Update skill
        service = get_custom_skill_service()
        skill = service.update_skill(skill_id, content, user_id=user.id)

        return jsonify(
            {
                "success": True,
                "skill": skill.to_dict(),
                "message": f"Skill '{skill.name}' updated successfully",
            }
        )

    except SkillNotFoundError:
        return jsonify({"error": "Skill not found"}), 404
    except PermissionDeniedError as e:
        return jsonify({"error": str(e)}), 403
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error updating skill {skill_id}: {e}")
        return jsonify({"error": "Failed to update skill"}), 500


@skills_bp.route("/api/skills/<skill_id>", methods=["DELETE"])
@rate_limit("20 per hour")
@login_required
def api_delete_skill(skill_id: str):
    """Delete a skill."""
    try:
        if not validate_uuid(skill_id):
            return jsonify({"error": "Invalid skill ID"}), 400

        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401

        service = get_custom_skill_service()
        service.delete_skill(skill_id, user_id=user.id)

        return jsonify(
            {
                "success": True,
                "message": "Skill deleted successfully",
            }
        )

    except SkillNotFoundError:
        return jsonify({"error": "Skill not found"}), 404
    except PermissionDeniedError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        logger.error(f"Error deleting skill {skill_id}: {e}")
        return jsonify({"error": "Failed to delete skill"}), 500


@skills_bp.route("/api/skills/<skill_id>/share", methods=["POST"])
@rate_limit("10 per hour")
@login_required
def api_share_skill(skill_id: str):
    """
    Promote a private skill to team-shared.

    This creates a copy in the team's namespace.
    """
    try:
        if not validate_uuid(skill_id):
            return jsonify({"error": "Invalid skill ID"}), 400

        user = get_current_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401

        team_id = get_user_team_id()
        if not team_id:
            return jsonify({"error": "No team found. Cannot share skill."}), 400

        service = get_custom_skill_service()
        shared_skill = service.promote_to_shared(skill_id, team_id, user_id=user.id)

        return jsonify(
            {
                "success": True,
                "skill": shared_skill.to_dict(),
                "message": f"Skill '{shared_skill.name}' shared with team successfully",
            }
        )

    except SkillNotFoundError:
        return jsonify({"error": "Skill not found"}), 404
    except PermissionDeniedError as e:
        return jsonify({"error": str(e)}), 403
    except DuplicateSkillError as e:
        return jsonify({"error": str(e)}), 409
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error sharing skill {skill_id}: {e}")
        return jsonify({"error": "Failed to share skill"}), 500


@skills_bp.route("/api/skills/validate", methods=["POST"])
@rate_limit("60 per hour")
@login_required
def api_validate_skill():
    """
    Validate SKILL.md content without creating.

    Request (JSON):
        - content: SKILL.md content to validate

    Response:
        - valid: boolean
        - error: error message (if invalid)
        - metadata: extracted metadata (if valid)
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        content = data.get("content", "").strip()
        if not content:
            return jsonify({"error": "Content is required"}), 400

        service = get_custom_skill_service()
        is_valid, error, metadata = service.validate_skill_content(content)

        if is_valid:
            return jsonify(
                {
                    "valid": True,
                    "metadata": metadata,
                }
            )
        else:
            return jsonify(
                {
                    "valid": False,
                    "error": error,
                }
            )

    except Exception as e:
        logger.error(f"Error validating skill: {e}")
        return jsonify({"error": "Validation failed"}), 500
