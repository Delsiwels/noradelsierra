"""
AR/AP Aging Dashboard Blueprint

Routes for accounts receivable and payable aging analysis.

Endpoints:
- GET  /aging-dashboard/              - Render main page
- GET  /aging-dashboard/api/generate  - Generate aging data
- GET  /aging-dashboard/api/download  - Export to Excel
"""

import logging

from flask import (
    Blueprint,
    jsonify,
    render_template,
    request,
    send_file,
)

from webapp.app_services.aging_dashboard_service import (
    export_to_excel,
    generate_aging_dashboard,
)
from webapp.blueprints._helpers import (
    get_xero_credentials as _get_xero_credentials,
)
from webapp.blueprints._helpers import (
    login_required as _login_required,
)

logger = logging.getLogger(__name__)

aging_dashboard_bp = Blueprint(
    "aging_dashboard", __name__, url_prefix="/aging-dashboard"
)


# =============================================================================
# Page Route
# =============================================================================


@aging_dashboard_bp.route("/")
@_login_required
def index():
    """Render the aging dashboard page."""
    return render_template("aging_dashboard.html")


# =============================================================================
# API Routes
# =============================================================================


@aging_dashboard_bp.route("/api/generate", methods=["GET"])
@_login_required
def api_generate():
    """
    Generate AR/AP aging dashboard data.

    Query params:
        - as_at_date: Date for aging calculation (YYYY-MM-DD)

    Returns:
        Aging data with receivables, payables, summaries, and alerts
    """
    access_token, tenant_id = _get_xero_credentials()

    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    as_at_date = request.args.get("as_at_date")

    if not as_at_date:
        return jsonify({"error": "as_at_date is required"}), 400

    try:
        result = generate_aging_dashboard(access_token, tenant_id, as_at_date)
        return jsonify(result)
    except Exception as e:
        logger.exception("Error generating aging dashboard: %s", e)
        return jsonify({"error": "Failed to generate aging data"}), 500


@aging_dashboard_bp.route("/api/download", methods=["GET"])
@_login_required
def api_download():
    """
    Download aging dashboard as Excel.

    Query params:
        - as_at_date: Date for aging calculation (YYYY-MM-DD)

    Returns:
        Excel file download
    """
    access_token, tenant_id = _get_xero_credentials()

    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    as_at_date = request.args.get("as_at_date")

    if not as_at_date:
        return jsonify({"error": "as_at_date is required"}), 400

    try:
        result = generate_aging_dashboard(access_token, tenant_id, as_at_date)

        if not result.get("success"):
            return jsonify({"error": result.get("error", "Generation failed")}), 500

        excel_file = export_to_excel(result)

        filename = f"aging_dashboard_{as_at_date}.xlsx"
        return send_file(
            excel_file,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        logger.exception("Error downloading aging dashboard: %s", e)
        return jsonify({"error": "Failed to download aging data"}), 500
