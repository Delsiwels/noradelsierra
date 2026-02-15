"""
Readiness Blueprint

REST API and page endpoints for month-end and EOFY readiness checks.

Endpoints:
- GET /api/readiness/checklist - Get current applicable checklist
- PUT /api/readiness/checklist - Update checklist progress
- GET /api/readiness/history - Past completed checklists
- GET /api/readiness/status - Quick completion status
- GET /api/readiness/team-members - Team members for assignment dropdown
- POST /api/readiness/comments - Add a comment to a checklist item
- GET /api/readiness/comments - Get comments for a checklist
- GET /readiness - Checklist page
- GET /readiness/history - History page
"""

import logging

from flask import Blueprint, jsonify, render_template, request, session
from flask_login import current_user, login_required

from webapp.models import ChecklistProgress, User, db

logger = logging.getLogger(__name__)

readiness_bp = Blueprint("readiness", __name__)


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


def _get_tenant() -> tuple[str | None, str | None]:
    """Read tenant_id / tenant_name from session's Xero connection."""
    conn: dict = session.get("xero_connection", {})
    return conn.get("tenant_id"), conn.get("tenant_name")


@readiness_bp.route("/readiness")
@login_required
def checklist_page():
    """Render the checklist page."""
    return render_template("readiness/checklist.html")


@readiness_bp.route("/readiness/history")
@login_required
def history_page():
    """Render the checklist history page."""
    return render_template("readiness/history.html")


@readiness_bp.route("/api/readiness/checklist", methods=["GET"])
@login_required
def api_get_checklist():
    """
    Get the current applicable checklist with any saved progress.

    Returns EOFY checklist in May-July, month-end otherwise.
    """
    try:
        team_id = current_user.team_id
        if not team_id:
            return jsonify({"error": "No team found"}), 400

        tenant_id, tenant_name = _get_tenant()

        from webapp.services.readiness_checks import get_current_checklist

        checklist = get_current_checklist(
            team_id,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
        )

        return jsonify(
            {
                "success": True,
                "checklist": checklist,
            }
        )

    except Exception as e:
        logger.exception(f"Error getting checklist: {e}")
        return jsonify({"error": "Failed to get checklist"}), 500


@readiness_bp.route("/api/readiness/checklist", methods=["PUT"])
@login_required
def api_update_checklist():
    """
    Update checklist progress (toggle items).

    Request (JSON):
        - checklist_type: "month_end" or "eofy"
        - period: Period string (YYYY-MM)
        - items: List of item dicts with key and completed status
    """
    try:
        team_id = current_user.team_id
        if not team_id:
            return jsonify({"error": "No team found"}), 400

        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        checklist_type = data.get("checklist_type")
        if checklist_type not in ("month_end", "eofy"):
            return (
                jsonify({"error": "checklist_type must be 'month_end' or 'eofy'"}),
                400,
            )

        period = data.get("period")
        if not period:
            return jsonify({"error": "period is required"}), 400

        items = data.get("items")
        if not items or not isinstance(items, list):
            return jsonify({"error": "items list is required"}), 400

        tenant_id, tenant_name = _get_tenant()

        from webapp.services.readiness_checks import save_checklist_progress

        progress = save_checklist_progress(
            team_id=team_id,
            user_id=current_user.id,
            checklist_type=checklist_type,
            period=period,
            items=items,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
        )

        return jsonify(
            {
                "success": True,
                "progress": progress.to_dict(),
            }
        )

    except Exception as e:
        db.session.rollback()
        logger.exception(f"Error updating checklist: {e}")
        return jsonify({"error": "Failed to update checklist"}), 500


@readiness_bp.route("/api/readiness/history", methods=["GET"])
@login_required
def api_get_history():
    """Get past completed checklists."""
    try:
        team_id = current_user.team_id
        if not team_id:
            return jsonify({"success": True, "history": []})

        tenant_id, _ = _get_tenant()

        from webapp.services.readiness_checks import get_checklist_history

        limit = _parse_int_query_arg("limit", default=12, minimum=1, maximum=50)
        history = get_checklist_history(team_id, limit=limit, tenant_id=tenant_id)

        return jsonify(
            {
                "success": True,
                "history": history,
            }
        )

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception(f"Error getting history: {e}")
        return jsonify({"error": "Failed to get history"}), 500


@readiness_bp.route("/api/readiness/status", methods=["GET"])
@login_required
def api_get_status():
    """Quick status: X of Y items complete."""
    try:
        team_id = current_user.team_id
        if not team_id:
            return jsonify({"error": "No team found"}), 400

        tenant_id, tenant_name = _get_tenant()

        from webapp.services.readiness_checks import get_current_checklist

        checklist = get_current_checklist(
            team_id,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
        )

        return jsonify(
            {
                "success": True,
                "checklist_type": checklist["checklist_type"],
                "period": checklist["period"],
                "completed": checklist["completed"],
                "total": checklist["total"],
                "percentage": checklist["percentage"],
                "is_complete": checklist["is_complete"],
            }
        )

    except Exception as e:
        logger.exception(f"Error getting status: {e}")
        return jsonify({"error": "Failed to get status"}), 500


# -----------------------------------------------------------------------
# Team members (for assignment dropdown)
# -----------------------------------------------------------------------


@readiness_bp.route("/api/readiness/team-members", methods=["GET"])
@login_required
def api_team_members():
    """Return team members for the assign-to dropdown."""
    try:
        team_id = current_user.team_id
        if not team_id:
            return jsonify({"members": []})

        members = User.query.filter_by(team_id=team_id, is_active=True).all()
        return jsonify(
            {
                "members": [
                    {
                        "user_id": m.id,
                        "full_name": m.name,
                        "email": m.email,
                        "role": m.role,
                    }
                    for m in members
                ]
            }
        )

    except Exception as e:
        logger.exception(f"Error getting team members: {e}")
        return jsonify({"error": "Failed to get team members"}), 500


# -----------------------------------------------------------------------
# Comments
# -----------------------------------------------------------------------


def _validate_checklist_ownership(
    checklist_progress_id: str, team_id: str
) -> ChecklistProgress | None:
    """Return the ChecklistProgress if it belongs to the team, else None."""
    return ChecklistProgress.query.filter_by(  # type: ignore[no-any-return]
        id=checklist_progress_id, team_id=team_id
    ).first()


@readiness_bp.route("/api/readiness/comments", methods=["POST"])
@login_required
def api_add_comment():
    """
    Add a comment/note to a checklist item.

    Request JSON:
        checklist_progress_id: str
        item_key: str
        content: str
        assigned_to: str | null  (user_id)
    """
    try:
        team_id = current_user.team_id
        if not team_id:
            return jsonify({"error": "No team found"}), 400

        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        checklist_progress_id = data.get("checklist_progress_id")
        if not checklist_progress_id:
            return jsonify({"error": "checklist_progress_id is required"}), 400

        # IDOR check: checklist must belong to user's team
        progress = _validate_checklist_ownership(checklist_progress_id, team_id)
        if not progress:
            return jsonify({"error": "Checklist not found"}), 404

        item_key = data.get("item_key", "")
        content = data.get("content", "")
        assigned_to = data.get("assigned_to") or None

        # Validate assigned_to is a team member
        if assigned_to:
            assignee = User.query.filter_by(
                id=assigned_to, team_id=team_id, is_active=True
            ).first()
            if not assignee:
                return jsonify({"error": "Assigned user is not a team member"}), 400

        from webapp.services.readiness_checks import add_checklist_comment

        comment = add_checklist_comment(
            checklist_progress_id=checklist_progress_id,
            item_key=item_key,
            user_id=current_user.id,
            content=content,
            assigned_to=assigned_to,
        )

        return jsonify({"success": True, "comment": comment.to_dict()})

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        db.session.rollback()
        logger.exception(f"Error adding comment: {e}")
        return jsonify({"error": "Failed to add comment"}), 500


@readiness_bp.route("/api/readiness/comments", methods=["GET"])
@login_required
def api_get_comments():
    """
    Get comments for a checklist, grouped by item_key.

    Query params:
        checklist_progress_id: str
    """
    try:
        team_id = current_user.team_id
        if not team_id:
            return jsonify({"error": "No team found"}), 400

        checklist_progress_id = request.args.get("checklist_progress_id")
        if not checklist_progress_id:
            return jsonify({"error": "checklist_progress_id is required"}), 400

        # IDOR check
        progress = _validate_checklist_ownership(checklist_progress_id, team_id)
        if not progress:
            return jsonify({"error": "Checklist not found"}), 404

        from webapp.services.readiness_checks import get_checklist_comments

        comments = get_checklist_comments(checklist_progress_id)

        return jsonify({"success": True, "comments": comments})

    except Exception as e:
        logger.exception(f"Error getting comments: {e}")
        return jsonify({"error": "Failed to get comments"}), 500
