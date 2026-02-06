"""
Payroll Tax Calculator Blueprint

Routes for state payroll tax calculations.

Endpoints:
- GET  /payroll-tax/              - Render main page
- GET  /payroll-tax/api/generate  - Generate payroll tax calculation
- GET  /payroll-tax/api/download  - Export to Excel
- GET  /payroll-tax/api/rates     - Get all state rates
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

from webapp.app_services.payroll_tax_service import (
    calculate_payroll_tax,
    export_to_excel,
    get_all_state_rates,
)

logger = logging.getLogger(__name__)

payroll_tax_bp = Blueprint("payroll_tax", __name__, url_prefix="/payroll-tax")


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


@payroll_tax_bp.route("/")
@_login_required
def index():
    """Render the payroll tax calculator page."""
    return render_template("payroll_tax.html")


@payroll_tax_bp.route("/api/generate", methods=["GET"])
@_login_required
def api_generate():
    """Generate payroll tax calculation."""
    access_token, tenant_id = _get_xero_credentials()

    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    state = request.args.get("state")

    if not from_date or not to_date:
        return jsonify({"error": "from_date and to_date are required"}), 400

    if not state:
        return jsonify({"error": "state is required"}), 400

    try:
        result = calculate_payroll_tax(
            access_token, tenant_id, from_date, to_date, state
        )
        return jsonify(result)
    except Exception as e:
        logger.exception("Error calculating payroll tax: %s", e)
        return jsonify({"error": "Failed to calculate payroll tax"}), 500


@payroll_tax_bp.route("/api/download", methods=["GET"])
@_login_required
def api_download():
    """Download payroll tax calculation as Excel."""
    access_token, tenant_id = _get_xero_credentials()

    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    state = request.args.get("state")

    if not from_date or not to_date or not state:
        return jsonify({"error": "from_date, to_date and state are required"}), 400

    try:
        result = calculate_payroll_tax(
            access_token, tenant_id, from_date, to_date, state
        )

        if not result.get("success"):
            return jsonify({"error": result.get("error", "Generation failed")}), 500

        excel_file = export_to_excel(result)

        filename = f"payroll_tax_{state}_{from_date}_to_{to_date}.xlsx"
        return send_file(
            excel_file,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        logger.exception("Error downloading payroll tax: %s", e)
        return jsonify({"error": "Failed to download"}), 500


@payroll_tax_bp.route("/api/rates", methods=["GET"])
@_login_required
def api_rates():
    """Get all state payroll tax rates."""
    return jsonify({"success": True, "rates": get_all_state_rates()})
