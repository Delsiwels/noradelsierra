"""
Export Blueprint

REST API endpoints for PDF export of conversations and compliance records.

Endpoints:
- GET /api/export/conversation/<id>/pdf - Download single conversation PDF
- GET /api/export/compliance/pdf - Download compliance summary PDF
- POST /api/export/bulk/pdf - Export multiple conversations in one PDF
"""

import logging

from flask import Blueprint, Response, jsonify, request
from flask_login import current_user, login_required

from webapp.models import AccountantShare, Conversation, User

logger = logging.getLogger(__name__)

export_bp = Blueprint("export", __name__)


def _can_access_conversation(conversation, user):
    """Check if user can access a conversation (owner or shared accountant)."""
    if conversation.user_id == user.id:
        return True

    # Check if user is on the same team
    if user.team_id:
        conv_owner = User.query.get(conversation.user_id)
        if conv_owner and conv_owner.team_id == user.team_id:
            return True

    # Check if accountant with shared access
    if user.role == "accountant":
        conv_owner = User.query.get(conversation.user_id)
        if conv_owner and conv_owner.team_id:
            share = AccountantShare.query.filter_by(
                team_id=conv_owner.team_id,
                accountant_user_id=user.id,
            ).first()
            if share and not share.is_expired():
                return True

    return False


@export_bp.route("/api/export/conversation/<conversation_id>/pdf", methods=["GET"])
@login_required
def api_export_conversation_pdf(conversation_id: str):
    """
    Download a single conversation as a PDF.

    Query params:
        - business_name: Optional business name for header
    """
    try:
        conversation = Conversation.query.get(conversation_id)
        if not conversation:
            return jsonify({"error": "Conversation not found"}), 404

        if not _can_access_conversation(conversation, current_user):
            return jsonify({"error": "Access denied"}), 403

        business_name = request.args.get("business_name", "")

        from webapp.services.pdf_export import export_conversation

        pdf_bytes = export_conversation(conversation_id, business_name=business_name)

        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="conversation-{conversation_id[:8]}.pdf"'
            },
        )

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.exception(f"Error exporting conversation PDF: {e}")
        return jsonify({"error": "Failed to export PDF"}), 500


@export_bp.route("/api/export/compliance/pdf", methods=["GET"])
@login_required
def api_export_compliance_pdf():
    """
    Download a compliance summary PDF.

    Query params:
        - date_from: Start date YYYY-MM-DD (optional)
        - date_to: End date YYYY-MM-DD (optional)
        - business_name: Optional business name
    """
    try:
        team_id = current_user.team_id

        # Accountants can export for shared teams
        if not team_id and current_user.role == "accountant":
            shared_team_id = request.args.get("team_id")
            if shared_team_id:
                share = AccountantShare.query.filter_by(
                    team_id=shared_team_id,
                    accountant_user_id=current_user.id,
                ).first()
                if share and not share.is_expired():
                    team_id = shared_team_id

        if not team_id:
            return jsonify({"error": "No team found"}), 400

        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")
        business_name = request.args.get("business_name", "")

        from webapp.services.pdf_export import export_compliance_summary

        pdf_bytes = export_compliance_summary(
            team_id, date_from=date_from, date_to=date_to, business_name=business_name
        )

        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="compliance-summary.pdf"'
            },
        )

    except Exception as e:
        logger.exception(f"Error exporting compliance PDF: {e}")
        return jsonify({"error": "Failed to export PDF"}), 500


@export_bp.route("/api/export/bulk/pdf", methods=["POST"])
@login_required
def api_export_bulk_pdf():
    """
    Export multiple conversations in one PDF.

    Request (JSON):
        - conversation_ids: List of conversation IDs
        - business_name: Optional business name
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        conversation_ids = data.get("conversation_ids", [])
        if not conversation_ids or not isinstance(conversation_ids, list):
            return jsonify({"error": "conversation_ids list is required"}), 400

        if len(conversation_ids) > 50:
            return jsonify({"error": "Maximum 50 conversations per export"}), 400

        # Verify access to all conversations
        accessible_ids = []
        for cid in conversation_ids:
            conversation = Conversation.query.get(cid)
            if conversation and _can_access_conversation(conversation, current_user):
                accessible_ids.append(cid)

        if not accessible_ids:
            return jsonify({"error": "No accessible conversations found"}), 404

        business_name = data.get("business_name", "")

        from webapp.services.pdf_export import export_bulk_conversations

        pdf_bytes = export_bulk_conversations(
            accessible_ids, business_name=business_name
        )

        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="bulk-export.pdf"'},
        )

    except Exception as e:
        logger.exception(f"Error exporting bulk PDF: {e}")
        return jsonify({"error": "Failed to export PDF"}), 500
