"""
Sharing Blueprint

REST API endpoints for accountant sharing / collaboration.

Endpoints:
- POST /api/sharing/invite - Owner invites accountant by email
- GET /api/sharing/invites - List active shares for team
- DELETE /api/sharing/invites/<id> - Revoke access
- GET /api/sharing/shared-with-me - Accountant sees shared teams
- GET /sharing/manage - Manage sharing page
- GET /sharing/dashboard - Accountant shared dashboard page
"""

import logging
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request
from flask_bcrypt import generate_password_hash
from flask_login import current_user, login_required

from webapp.models import AccountantShare, Team, User, db
from webapp.utils import sanitize_input, validate_email

logger = logging.getLogger(__name__)

sharing_bp = Blueprint("sharing", __name__)


def _require_owner_or_admin():
    """Check that current user is owner or admin. Returns error response or None."""
    if current_user.role not in ("owner", "admin"):
        return jsonify({"error": "Only team owners and admins can manage sharing"}), 403
    return None


@sharing_bp.route("/sharing/manage")
@login_required
def manage_page():
    """Render sharing management page."""
    return render_template("sharing/manage.html")


@sharing_bp.route("/sharing/dashboard")
@login_required
def shared_dashboard_page():
    """Render accountant shared dashboard."""
    return render_template("sharing/shared_dashboard.html")


@sharing_bp.route("/api/sharing/invite", methods=["POST"])
@login_required
def api_invite_accountant():
    """
    Invite an accountant by email. Creates account if needed.

    Request (JSON):
        - email: Accountant email (required)
        - name: Accountant name (required if new account)
        - expires_days: Optional days until access expires

    Response:
        - success: boolean
        - share: Share info dict
    """
    try:
        error = _require_owner_or_admin()
        if error:
            return error

        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        email = (data.get("email") or "").strip().lower()
        name = sanitize_input((data.get("name") or "").strip())
        expires_days = data.get("expires_days")

        if not email or not validate_email(email):
            return jsonify({"error": "Valid email is required"}), 400

        team_id = current_user.team_id
        if not team_id:
            return jsonify({"error": "You must belong to a team"}), 400

        # Find or create accountant user
        accountant = User.query.filter_by(email=email).first()
        if not accountant:
            if not name:
                return jsonify({"error": "Name is required for new accountant"}), 400

            # Create accountant account with a random password (they'll need to reset)
            import secrets

            temp_password = secrets.token_urlsafe(16)
            pw_hash = generate_password_hash(temp_password).decode("utf-8")

            accountant = User(
                email=email,
                password_hash=pw_hash,
                name=name,
                role="accountant",
                is_active=True,
            )
            db.session.add(accountant)
            db.session.flush()

        # Check for existing share
        existing = AccountantShare.query.filter_by(
            team_id=team_id, accountant_user_id=accountant.id
        ).first()
        if existing:
            return (
                jsonify({"error": "This accountant already has access to your team"}),
                409,
            )

        expires_at = None
        if expires_days and int(expires_days) > 0:
            from datetime import timedelta

            expires_at = datetime.utcnow() + timedelta(days=int(expires_days))

        share = AccountantShare(
            team_id=team_id,
            accountant_user_id=accountant.id,
            shared_by_user_id=current_user.id,
            access_level="read_only",
            expires_at=expires_at,
        )
        db.session.add(share)
        db.session.commit()

        return jsonify({"success": True, "share": share.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        logger.exception(f"Error inviting accountant: {e}")
        return jsonify({"error": "Failed to invite accountant"}), 500


@sharing_bp.route("/api/sharing/invites", methods=["GET"])
@login_required
def api_list_invites():
    """List active shares for the current user's team."""
    try:
        team_id = current_user.team_id
        if not team_id:
            return jsonify({"success": True, "shares": []})

        shares = AccountantShare.query.filter_by(team_id=team_id).all()
        return jsonify(
            {
                "success": True,
                "shares": [s.to_dict() for s in shares if not s.is_expired()],
            }
        )

    except Exception as e:
        logger.exception(f"Error listing invites: {e}")
        return jsonify({"error": "Failed to list invites"}), 500


@sharing_bp.route("/api/sharing/invites/<share_id>", methods=["DELETE"])
@login_required
def api_revoke_invite(share_id: str):
    """Revoke an accountant's access."""
    try:
        error = _require_owner_or_admin()
        if error:
            return error

        share = AccountantShare.query.get(share_id)
        if not share:
            return jsonify({"error": "Share not found"}), 404

        if share.team_id != current_user.team_id:
            return jsonify({"error": "Access denied"}), 403

        db.session.delete(share)
        db.session.commit()

        return jsonify({"success": True})

    except Exception as e:
        db.session.rollback()
        logger.exception(f"Error revoking invite: {e}")
        return jsonify({"error": "Failed to revoke invite"}), 500


@sharing_bp.route("/api/sharing/shared-with-me", methods=["GET"])
@login_required
def api_shared_with_me():
    """List teams shared with the current accountant user."""
    try:
        shares = AccountantShare.query.filter_by(
            accountant_user_id=current_user.id
        ).all()

        result = []
        for share in shares:
            if share.is_expired():
                continue
            team = Team.query.get(share.team_id)
            if team:
                result.append(
                    {
                        "share_id": share.id,
                        "team": team.to_dict(),
                        "access_level": share.access_level,
                        "shared_at": share.created_at.isoformat()
                        if share.created_at
                        else None,
                        "expires_at": share.expires_at.isoformat()
                        if share.expires_at
                        else None,
                    }
                )

        return jsonify({"success": True, "shared_teams": result})

    except Exception as e:
        logger.exception(f"Error getting shared teams: {e}")
        return jsonify({"error": "Failed to get shared teams"}), 500
