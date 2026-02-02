"""
Super Reconciliation Blueprint

Page routes and REST API endpoints for super guarantee reconciliation.

Endpoints:
- GET /super-reconciliation - Render page
- GET /super-reconciliation/api/generate - Run reconciliation
- POST /super-reconciliation/api/send-reminder - Send email reminder
- GET /super-reconciliation/api/download - Download CSV
- GET /super-reconciliation/api/client-email - Get saved client email
- POST /super-reconciliation/api/client-email - Save client email
"""

import csv
import io
import logging
import re
from datetime import date

from flask import Blueprint, Response, jsonify, render_template, request
from flask_login import current_user, login_required

from webapp.models import Team, db

logger = logging.getLogger(__name__)

super_recon_bp = Blueprint(
    "super_reconciliation", __name__, url_prefix="/super-reconciliation"
)


def _validate_date(date_str: str) -> date | None:
    """Validate and parse a YYYY-MM-DD date string."""
    if not date_str or not isinstance(date_str, str):
        return None
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        return None


def _validate_email(email: str) -> bool:
    """Basic email validation."""
    if not email or not isinstance(email, str):
        return False
    return bool(re.match(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$", email))


# =============================================================================
# Page Routes
# =============================================================================


@super_recon_bp.route("/")
@login_required
def super_reconciliation_page():
    """Render the super reconciliation page."""
    return render_template("super_reconciliation.html")


# =============================================================================
# API Routes
# =============================================================================


@super_recon_bp.route("/api/generate", methods=["GET"])
@login_required
def api_generate_reconciliation():
    """
    Run super guarantee reconciliation for a date range.

    Query params:
        - from_date: Start date (YYYY-MM-DD)
        - to_date: End date (YYYY-MM-DD)
        - access_token: Xero access token
        - tenant_id: Xero tenant ID

    Response:
        - success: bool
        - sg_info, summary, employees, payments
    """
    try:
        from_date = _validate_date(request.args.get("from_date", ""))
        to_date = _validate_date(request.args.get("to_date", ""))

        if not from_date or not to_date:
            return (
                jsonify(
                    {"error": "Valid from_date and to_date are required (YYYY-MM-DD)"}
                ),
                400,
            )

        if from_date > to_date:
            return jsonify({"error": "from_date must be before to_date"}), 400

        if (to_date - from_date).days > 366:
            return jsonify({"error": "Date range cannot exceed one year"}), 400

        access_token = request.args.get("access_token", "")
        tenant_id = request.args.get("tenant_id", "")

        if not access_token or not tenant_id:
            return (
                jsonify({"error": "Xero access_token and tenant_id are required"}),
                400,
            )

        from webapp.app_services.super_reconciliation_service import (
            generate_super_reconciliation,
        )

        result = generate_super_reconciliation(
            access_token=access_token,
            tenant_id=tenant_id,
            from_date=from_date,
            to_date=to_date,
        )

        return jsonify(result)

    except Exception as e:
        logger.exception("Error generating super reconciliation: %s", e)
        return jsonify({"error": "Failed to generate reconciliation"}), 500


@super_recon_bp.route("/api/send-reminder", methods=["POST"])
@login_required
def api_send_reminder():
    """
    Send a super guarantee reminder email.

    Request (JSON):
        - email: Recipient email
        - quarter_label: e.g. "Q1 Jul-Sep 2024"
        - deadline: Deadline display string
        - total_liability: float
        - total_paid: float
        - variance: float
        - status: pass/warning/fail
        - tenant_name: Organisation name
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        email = (data.get("email") or "").strip()
        if not _validate_email(email):
            return jsonify({"error": "Valid email address is required"}), 400

        quarter_label = str(data.get("quarter_label", ""))
        deadline = str(data.get("deadline", ""))
        tenant_name = str(data.get("tenant_name", ""))

        if not quarter_label or not deadline or not tenant_name:
            return (
                jsonify(
                    {"error": "quarter_label, deadline, and tenant_name are required"}
                ),
                400,
            )

        total_liability = float(data.get("total_liability", 0))
        total_paid = float(data.get("total_paid", 0))
        variance = float(data.get("variance", 0))
        status = str(data.get("status", "warning"))

        from webapp.app_services.super_reconciliation_service import (
            send_super_reminder_email,
        )

        result = send_super_reminder_email(
            to_email=email,
            quarter_label=quarter_label,
            deadline=deadline,
            total_liability=total_liability,
            total_paid=total_paid,
            variance=variance,
            status=status,
            tenant_name=tenant_name,
        )

        return jsonify(result)

    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid numeric value: {e}"}), 400
    except Exception as e:
        logger.exception("Error sending super reminder: %s", e)
        return jsonify({"error": "Failed to send reminder"}), 500


@super_recon_bp.route("/api/download", methods=["GET"])
@login_required
def api_download_csv():
    """
    Download super reconciliation data as CSV.

    Query params: same as /api/generate
    """
    try:
        from_date = _validate_date(request.args.get("from_date", ""))
        to_date = _validate_date(request.args.get("to_date", ""))

        if not from_date or not to_date:
            return jsonify({"error": "Valid from_date and to_date are required"}), 400

        access_token = request.args.get("access_token", "")
        tenant_id = request.args.get("tenant_id", "")

        if not access_token or not tenant_id:
            return jsonify({"error": "Xero credentials required"}), 400

        from webapp.app_services.super_reconciliation_service import (
            generate_super_reconciliation,
        )

        result = generate_super_reconciliation(
            access_token=access_token,
            tenant_id=tenant_id,
            from_date=from_date,
            to_date=to_date,
        )

        if not result["success"]:
            return jsonify({"error": result.get("error", "Reconciliation failed")}), 500

        # Build CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Header info
        sg_info = result["sg_info"]
        summary = result["summary"]
        writer.writerow(["Super Guarantee Reconciliation"])
        writer.writerow(["Quarter", sg_info["label"]])
        writer.writerow(["SG Rate", sg_info["sg_rate_display"]])
        writer.writerow(["Deadline", sg_info["deadline_display"]])
        writer.writerow(["Status", summary["status_label"]])
        writer.writerow([])

        # Summary
        writer.writerow(["Summary"])
        writer.writerow(["Total SG Liability", f"${summary['total_liability']:,.2f}"])
        writer.writerow(["Total Super Paid", f"${summary['total_paid']:,.2f}"])
        writer.writerow(["Variance", f"${summary['variance']:,.2f}"])
        writer.writerow([])

        # Employee breakdown
        writer.writerow(["Employee Breakdown"])
        writer.writerow(
            ["Employee", "Gross Earnings", "SG Rate", "Expected Super", "Payslip Super"]
        )
        for emp in result["employees"]:
            writer.writerow(
                [
                    emp["name"],
                    f"${emp['gross_earnings']:,.2f}",
                    f"{emp['sg_rate'] * 100:.1f}%",
                    f"${emp['expected_super']:,.2f}",
                    f"${emp['payslip_super']:,.2f}",
                ]
            )
        writer.writerow([])

        # Payments
        writer.writerow(["Super Payments"])
        writer.writerow(["Date", "Description", "Account", "Amount", "Status"])
        for pay in result["payments"]:
            writer.writerow(
                [
                    pay["date_display"],
                    pay["description"],
                    pay["account_name"],
                    f"${pay['amount']:,.2f}",
                    "LATE" if pay["is_late"] else "On Time",
                ]
            )

        csv_content = output.getvalue()
        output.close()

        filename = f"super_reconciliation_{sg_info['label'].replace(' ', '_')}.csv"

        return Response(
            csv_content,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as e:
        logger.exception("Error downloading CSV: %s", e)
        return jsonify({"error": "Failed to generate CSV"}), 500


@super_recon_bp.route("/api/client-email", methods=["GET"])
@login_required
def api_get_client_email():
    """Get the saved default client email for the team."""
    try:
        team_id = current_user.team_id
        if not team_id:
            return jsonify({"success": True, "email": None})

        team = db.session.get(Team, team_id)
        if not team:
            return jsonify({"success": True, "email": None})

        return jsonify({"success": True, "email": team.client_email})

    except Exception as e:
        logger.exception("Error getting client email: %s", e)
        return jsonify({"error": "Failed to get client email"}), 500


@super_recon_bp.route("/api/client-email", methods=["POST"])
@login_required
def api_save_client_email():
    """Save the default client email for the team."""
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON body required"}), 400

        email = (data.get("email") or "").strip()
        if not _validate_email(email):
            return jsonify({"error": "Valid email address is required"}), 400

        team_id = current_user.team_id
        if not team_id:
            return jsonify({"error": "No team found"}), 400

        team = db.session.get(Team, team_id)
        if not team:
            return jsonify({"error": "Team not found"}), 404

        team.client_email = email
        db.session.commit()

        return jsonify({"success": True, "email": email})

    except Exception as e:
        db.session.rollback()
        logger.exception("Error saving client email: %s", e)
        return jsonify({"error": "Failed to save client email"}), 500
