"""
Readiness Blueprint

REST API and page endpoints for month-end and EOFY readiness checks.

Endpoints:
- GET /api/readiness/checklist - Get current applicable checklist
- PUT /api/readiness/checklist - Update checklist progress
- GET /api/readiness/history - Past completed checklists
- GET /api/readiness/status - Quick completion status
- GET /readiness - Checklist page
- GET /readiness/history - History page
"""

import logging

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from webapp.models import db

logger = logging.getLogger(__name__)

readiness_bp = Blueprint("readiness", __name__)


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

        from webapp.services.readiness_checks import get_current_checklist

        checklist = get_current_checklist(team_id)

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

        from webapp.services.readiness_checks import save_checklist_progress

        progress = save_checklist_progress(
            team_id=team_id,
            user_id=current_user.id,
            checklist_type=checklist_type,
            period=period,
            items=items,
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

        from webapp.services.readiness_checks import get_checklist_history

        limit = min(int(request.args.get("limit", 12)), 50)
        history = get_checklist_history(team_id, limit=limit)

        return jsonify(
            {
                "success": True,
                "history": history,
            }
        )

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

        from webapp.services.readiness_checks import get_current_checklist

        checklist = get_current_checklist(team_id)

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
