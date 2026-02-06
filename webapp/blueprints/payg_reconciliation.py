"""
PAYG-W Reconciliation Blueprint

Routes for PAYG withholding reconciliation between payroll and BAS.

Endpoints:
- GET  /payg-reconciliation/              - Render main page
- GET  /payg-reconciliation/api/generate  - Generate reconciliation data
- GET  /payg-reconciliation/api/download  - Export to Excel
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

from webapp.app_services.payg_reconciliation_service import (
    export_to_excel,
    generate_payg_reconciliation,
)

logger = logging.getLogger(__name__)

payg_reconciliation_bp = Blueprint(
    "payg_reconciliation", __name__, url_prefix="/payg-reconciliation"
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


@payg_reconciliation_bp.route("/")
@_login_required
def index():
    """Render the PAYG-W reconciliation page."""
    return render_template("payg_reconciliation.html")


# =============================================================================
# API Routes
# =============================================================================


@payg_reconciliation_bp.route("/api/generate", methods=["GET"])
@_login_required
def api_generate():
    """
    Generate PAYG-W reconciliation data.

    Query params:
        - from_date: Start date (YYYY-MM-DD)
        - to_date: End date (YYYY-MM-DD)

    Returns:
        Reconciliation data with payroll totals, BAS comparison, and variance
    """
    access_token, tenant_id = _get_xero_credentials()

    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    if not from_date or not to_date:
        return jsonify({"error": "from_date and to_date are required"}), 400

    try:
        result = generate_payg_reconciliation(
            access_token, tenant_id, from_date, to_date
        )
        return jsonify(result)
    except Exception as e:
        logger.exception("Error generating PAYG reconciliation: %s", e)
        return jsonify({"error": "Failed to generate reconciliation"}), 500


@payg_reconciliation_bp.route("/api/download", methods=["GET"])
@_login_required
def api_download():
    """
    Download PAYG-W reconciliation as Excel.

    Query params:
        - from_date: Start date (YYYY-MM-DD)
        - to_date: End date (YYYY-MM-DD)

    Returns:
        Excel file download
    """
    access_token, tenant_id = _get_xero_credentials()

    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    if not from_date or not to_date:
        return jsonify({"error": "from_date and to_date are required"}), 400

    try:
        result = generate_payg_reconciliation(
            access_token, tenant_id, from_date, to_date
        )

        if not result.get("success"):
            return jsonify({"error": result.get("error", "Generation failed")}), 500

        excel_file = export_to_excel(result)

        filename = f"payg_reconciliation_{from_date}_to_{to_date}.xlsx"
        return send_file(
            excel_file,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        logger.exception("Error downloading PAYG reconciliation: %s", e)
        return jsonify({"error": "Failed to download reconciliation"}), 500
