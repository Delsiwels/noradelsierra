"""
Fuel Tax Credits Calculator Blueprint

Routes for FTC calculations.

Endpoints:
- GET  /fuel-tax-credits/              - Render main page
- GET  /fuel-tax-credits/api/generate  - Generate FTC calculation
- GET  /fuel-tax-credits/api/download  - Export to Excel
- GET  /fuel-tax-credits/api/rates     - Get FTC rates
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

from webapp.app_services.fuel_tax_credits_service import (
    calculate_fuel_tax_credits,
    export_to_excel,
    get_ftc_rates,
)

logger = logging.getLogger(__name__)

fuel_tax_credits_bp = Blueprint(
    "fuel_tax_credits", __name__, url_prefix="/fuel-tax-credits"
)


def _login_required(f):
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
    conn = session.get("xero_connection", {})
    access_token = conn.get("access_token") or session.get("xero_access_token")
    tenant_id = conn.get("tenant_id") or session.get("xero_tenant_id")
    return access_token, tenant_id


@fuel_tax_credits_bp.route("/")
@_login_required
def index():
    return render_template("fuel_tax_credits.html")


@fuel_tax_credits_bp.route("/api/generate", methods=["GET"])
@_login_required
def api_generate():
    access_token, tenant_id = _get_xero_credentials()
    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    fuel_type = request.args.get("fuel_type", "heavy_vehicle")
    manual_litres = request.args.get("litres")

    if not from_date or not to_date:
        return jsonify({"error": "from_date and to_date are required"}), 400

    litres = None
    if manual_litres:
        try:
            litres = float(manual_litres)
        except ValueError:
            return jsonify({"error": "Invalid litres value"}), 400

    try:
        result = calculate_fuel_tax_credits(
            access_token, tenant_id, from_date, to_date, fuel_type, litres
        )
        return jsonify(result)
    except Exception as e:
        logger.exception("Error calculating FTC: %s", e)
        return jsonify({"error": "Failed to calculate FTC"}), 500


@fuel_tax_credits_bp.route("/api/download", methods=["GET"])
@_login_required
def api_download():
    access_token, tenant_id = _get_xero_credentials()
    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    fuel_type = request.args.get("fuel_type", "heavy_vehicle")

    if not from_date or not to_date:
        return jsonify({"error": "from_date and to_date are required"}), 400

    try:
        result = calculate_fuel_tax_credits(
            access_token, tenant_id, from_date, to_date, fuel_type
        )
        if not result.get("success"):
            return jsonify({"error": result.get("error", "Failed")}), 500

        excel_file = export_to_excel(result)
        filename = f"fuel_tax_credits_{from_date}_to_{to_date}.xlsx"
        return send_file(
            excel_file,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        logger.exception("Error downloading FTC: %s", e)
        return jsonify({"error": "Failed to download"}), 500


@fuel_tax_credits_bp.route("/api/rates", methods=["GET"])
@_login_required
def api_rates():
    return jsonify({"success": True, "rates": get_ftc_rates()})
