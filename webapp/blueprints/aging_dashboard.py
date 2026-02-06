"""
AR/AP Aging Dashboard Blueprint

Routes for accounts receivable and payable aging analysis.

Endpoints:
- GET  /aging-dashboard/              - Render main page
- GET  /aging-dashboard/api/generate  - Generate aging data
- GET  /aging-dashboard/api/download  - Export to Excel
"""

import logging
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

from webapp.app_services.aging_dashboard_service import (
    export_to_excel,
    generate_aging_dashboard,
)

logger = logging.getLogger(__name__)

aging_dashboard_bp = Blueprint(
    "aging_dashboard", __name__, url_prefix="/aging-dashboard"
)


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
