"""
STP Submission Tracker Blueprint

Routes for STP lodgement status and payroll totals tracking.

Endpoints:
- GET  /stp-tracker/              - Render main page
- GET  /stp-tracker/api/generate  - Generate STP summary
- GET  /stp-tracker/api/download  - Export to Excel
"""

import logging
from datetime import datetime
from functools import wraps

from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    send_file,
    session,
)

from webapp.app_services.stp_tracker_service import (
    export_to_excel,
    generate_stp_summary,
)

logger = logging.getLogger(__name__)

stp_tracker_bp = Blueprint("stp_tracker", __name__, url_prefix="/stp-tracker")


def _login_required(f):
    """Require login decorator. Bypassed in testing mode."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_app.config.get("TESTING"):
            return f(*args, **kwargs)
        try:
            from flask_login import current_user

            if not current_user.is_authenticated:
                return jsonify({"error": "Authentication required"}), 401
        except (ImportError, AttributeError):
            pass
        return f(*args, **kwargs)

    return decorated_function


def _get_xero_credentials() -> tuple[str | None, str | None]:
    """Get Xero access token and tenant ID from session."""
    conn = session.get("xero_connection", {})
    access_token = conn.get("access_token") or session.get("xero_access_token")
    tenant_id = conn.get("tenant_id") or session.get("xero_tenant_id")
    return access_token, tenant_id


@stp_tracker_bp.route("/")
@_login_required
def index():
    """Render the STP tracker page."""
    return render_template("stp_tracker.html")


@stp_tracker_bp.route("/api/generate", methods=["GET"])
@_login_required
def api_generate():
    """Generate STP summary for a financial year."""
    access_token, tenant_id = _get_xero_credentials()

    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    fy = request.args.get("financial_year")

    if not fy:
        # Default to current FY
        now = datetime.now()
        fy = now.year if now.month >= 7 else now.year

    try:
        financial_year = int(fy)
    except ValueError:
        return jsonify({"error": "Invalid financial_year"}), 400

    try:
        result = generate_stp_summary(access_token, tenant_id, financial_year)
        return jsonify(result)
    except Exception as e:
        logger.exception("Error generating STP summary: %s", e)
        return jsonify({"error": "Failed to generate STP summary"}), 500


@stp_tracker_bp.route("/api/download", methods=["GET"])
@_login_required
def api_download():
    """Download STP summary as Excel."""
    access_token, tenant_id = _get_xero_credentials()

    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    fy = request.args.get("financial_year")

    if not fy:
        now = datetime.now()
        fy = now.year if now.month >= 7 else now.year

    try:
        financial_year = int(fy)
    except ValueError:
        return jsonify({"error": "Invalid financial_year"}), 400

    try:
        result = generate_stp_summary(access_token, tenant_id, financial_year)

        if not result.get("success"):
            return jsonify({"error": result.get("error", "Generation failed")}), 500

        excel_file = export_to_excel(result)

        filename = f"stp_summary_fy{financial_year - 1}_{financial_year}.xlsx"
        return send_file(
            excel_file,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        logger.exception("Error downloading STP summary: %s", e)
        return jsonify({"error": "Failed to download"}), 500
