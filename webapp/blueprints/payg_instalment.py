"""
PAYG-I Calculator Blueprint

Routes for PAYG instalment calculations.

Endpoints:
- GET  /payg-instalment/              - Render main page
- GET  /payg-instalment/api/generate  - Generate instalment calculation
- GET  /payg-instalment/api/download  - Export to Excel
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

from webapp.app_services.payg_instalment_service import (
    calculate_payg_instalment,
    export_to_excel,
)

logger = logging.getLogger(__name__)

payg_instalment_bp = Blueprint(
    "payg_instalment", __name__, url_prefix="/payg-instalment"
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


@payg_instalment_bp.route("/")
@_login_required
def index():
    """Render the PAYG-I calculator page."""
    return render_template("payg_instalment.html")


@payg_instalment_bp.route("/api/generate", methods=["GET"])
@_login_required
def api_generate():
    """Generate PAYG instalment calculation."""
    access_token, tenant_id = _get_xero_credentials()

    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    rate = request.args.get("rate")
    method = request.args.get("method", "rate")

    if not from_date or not to_date:
        return jsonify({"error": "from_date and to_date are required"}), 400

    instalment_rate = None
    if rate:
        try:
            instalment_rate = float(rate) / 100  # Convert percentage to decimal
        except ValueError:
            return jsonify({"error": "Invalid rate value"}), 400

    try:
        result = calculate_payg_instalment(
            access_token, tenant_id, from_date, to_date, instalment_rate, method
        )
        return jsonify(result)
    except Exception as e:
        logger.exception("Error calculating PAYG instalment: %s", e)
        return jsonify({"error": "Failed to calculate instalment"}), 500


@payg_instalment_bp.route("/api/download", methods=["GET"])
@_login_required
def api_download():
    """Download PAYG instalment calculation as Excel."""
    access_token, tenant_id = _get_xero_credentials()

    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    if not from_date or not to_date:
        return jsonify({"error": "from_date and to_date are required"}), 400

    try:
        result = calculate_payg_instalment(access_token, tenant_id, from_date, to_date)

        if not result.get("success"):
            return jsonify({"error": result.get("error", "Generation failed")}), 500

        excel_file = export_to_excel(result)

        filename = f"payg_instalment_{from_date}_to_{to_date}.xlsx"
        return send_file(
            excel_file,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        logger.exception("Error downloading PAYG instalment: %s", e)
        return jsonify({"error": "Failed to download"}), 500
