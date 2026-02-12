"""Ask Fin journal review blueprint."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from webapp.ai import get_chat_service
from webapp.services.journal_parser import (
    MAX_FILE_SIZE,
    format_entries_for_review,
    parse_journal_csv,
)

ask_fin_bp = Blueprint("ask_fin", __name__)


@ask_fin_bp.route("/ask-fin/tax-agent", methods=["GET"])
@login_required
def tax_agent_page():
    """Render a lightweight Ask Fin page for journal review."""
    display_name = getattr(current_user, "name", "") or "User"
    return render_template("ask_fin_tax_agent.html", display_name=display_name)


@ask_fin_bp.route("/api/ask-fin/review-journal", methods=["POST"])
@login_required
def review_journal():
    """Validate uploaded CSV journals and optionally request AI review."""
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "No file was uploaded."}), 400

    filename = uploaded.filename.lower().strip()
    if not filename.endswith(".csv"):
        return jsonify({"error": "CSV file is required."}), 400

    payload = uploaded.stream.read(MAX_FILE_SIZE + 1)
    if not payload:
        return jsonify({"error": "Uploaded CSV is empty."}), 400
    if len(payload) > MAX_FILE_SIZE:
        return jsonify({"error": "Uploaded file is too large."}), 400

    parsed = parse_journal_csv(payload)
    if parsed.error:
        return jsonify({"error": parsed.error, "warnings": parsed.warnings}), 400

    review_input = format_entries_for_review(parsed)

    # Keep endpoint boot-safe for environments without AI credentials.
    service = get_chat_service()
    if service is None:
        return (
            jsonify(
                {
                    "error": "AI service is unavailable.",
                    "journal_summary": review_input,
                    "warnings": parsed.warnings,
                }
            ),
            503,
        )

    user_id = getattr(current_user, "id", None)
    team_id = getattr(current_user, "team_id", None)
    review_prompt = (
        "Review this uploaded journal for account coding and GST issues. "
        "Highlight rows with potential misclassification and provide concise fixes.\n\n"
        f"{review_input}"
    )

    try:
        ai_response = service.send_message(
            user_message=review_prompt,
            user_id=user_id,
            team_id=team_id,
            persist=False,
        )
    except Exception:
        return (
            jsonify(
                {
                    "error": "AI review generation failed.",
                    "journal_summary": review_input,
                    "warnings": parsed.warnings,
                }
            ),
            503,
        )

    return jsonify(
        {
            "success": True,
            "journal_summary": review_input,
            "review": ai_response.content,
            "skills_used": ai_response.skills_used,
            "model": ai_response.model,
            "usage": ai_response.usage,
            "warnings": parsed.warnings,
        }
    )
