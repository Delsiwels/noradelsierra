"""
Reminders Blueprint

REST API endpoints for BAS deadline reminders.

Endpoints:
- GET /api/reminders/bas - Get current BAS deadline reminders
- GET /api/reminders/settings - Get reminder preferences
- PUT /api/reminders/settings - Update reminder preferences
"""

import logging

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from webapp.models import db

logger = logging.getLogger(__name__)

reminders_bp = Blueprint("reminders", __name__)


@reminders_bp.route("/api/reminders/bas", methods=["GET"])
@login_required
def api_get_bas_reminders():
    """
    Get current BAS deadline reminders for the logged-in user.

    Response:
        - success: boolean
        - reminders: List of upcoming deadlines
        - status: Overall status
    """
    try:
        from webapp.services.bas_deadlines import (
            get_deadline_status,
            get_reminders_for_user,
        )

        reminders = get_reminders_for_user(current_user.id)

        # Serialize date objects
        for r in reminders:
            if "period_end" in r:
                r["period_end"] = r["period_end"].isoformat()
            if "due_date" in r:
                r["due_date"] = r["due_date"].isoformat()

        status = get_deadline_status(
            frequency=current_user.bas_frequency or "quarterly"
        )

        return jsonify(
            {
                "success": True,
                "reminders": reminders,
                "status": status,
                "frequency": current_user.bas_frequency or "quarterly",
            }
        )

    except Exception as e:
        logger.exception(f"Error getting BAS reminders: {e}")
        return jsonify({"error": "Failed to get reminders"}), 500


@reminders_bp.route("/api/reminders/settings", methods=["GET"])
@login_required
def api_get_reminder_settings():
    """Get reminder preferences for the current user."""
    return jsonify(
        {
            "success": True,
            "settings": {
                "bas_frequency": current_user.bas_frequency or "quarterly",
                "bas_reminders_enabled": current_user.bas_reminders_enabled,
            },
        }
    )


@reminders_bp.route("/api/reminders/settings", methods=["PUT"])
@login_required
def api_update_reminder_settings():
    """
    Update reminder preferences.

    Request (JSON):
        - bas_frequency: "quarterly" or "monthly"
        - bas_reminders_enabled: boolean
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        if "bas_frequency" in data:
            freq = data["bas_frequency"]
            if freq not in ("quarterly", "monthly"):
                return (
                    jsonify(
                        {"error": "bas_frequency must be 'quarterly' or 'monthly'"}
                    ),
                    400,
                )
            current_user.bas_frequency = freq

        if "bas_reminders_enabled" in data:
            current_user.bas_reminders_enabled = bool(data["bas_reminders_enabled"])

        db.session.commit()

        return jsonify(
            {
                "success": True,
                "settings": {
                    "bas_frequency": current_user.bas_frequency,
                    "bas_reminders_enabled": current_user.bas_reminders_enabled,
                },
            }
        )

    except Exception as e:
        db.session.rollback()
        logger.exception(f"Error updating reminder settings: {e}")
        return jsonify({"error": "Failed to update settings"}), 500
