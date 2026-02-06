"""
Depreciation Calculator Blueprint

Routes for calculating and reviewing quarterly depreciation.

Endpoints:
- GET  /depreciation-calc/              - Render main page
- GET  /depreciation-calc/api/generate  - Generate depreciation schedule
- GET  /depreciation-calc/api/download  - Export to Excel
- POST /depreciation-calc/api/calculate - Calculate single asset depreciation
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

from webapp.app_services.depreciation_calc_service import (
    calculate_depreciation,
    export_to_excel,
    generate_depreciation_schedule,
)

logger = logging.getLogger(__name__)

depreciation_calc_bp = Blueprint(
    "depreciation_calc", __name__, url_prefix="/depreciation-calc"
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


@depreciation_calc_bp.route("/")
@_login_required
def index():
    """Render the depreciation calculator page."""
    return render_template("depreciation_calc.html")


# =============================================================================
# API Routes
# =============================================================================


@depreciation_calc_bp.route("/api/generate", methods=["GET"])
@_login_required
def api_generate():
    """
    Generate depreciation schedule data.

    Query params:
        - from_date: Start date (YYYY-MM-DD)
        - to_date: End date (YYYY-MM-DD)

    Returns:
        Depreciation schedule with expected vs actual calculations
    """
    access_token, tenant_id = _get_xero_credentials()

    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    if not from_date or not to_date:
        return jsonify({"error": "from_date and to_date are required"}), 400

    try:
        result = generate_depreciation_schedule(
            access_token, tenant_id, from_date, to_date
        )
        return jsonify(result)
    except Exception as e:
        logger.exception("Error generating depreciation schedule: %s", e)
        return jsonify({"error": "Failed to generate depreciation schedule"}), 500


@depreciation_calc_bp.route("/api/download", methods=["GET"])
@_login_required
def api_download():
    """
    Download depreciation schedule as Excel.

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
        result = generate_depreciation_schedule(
            access_token, tenant_id, from_date, to_date
        )

        if not result.get("success"):
            return jsonify({"error": result.get("error", "Generation failed")}), 500

        excel_file = export_to_excel(result)

        filename = f"depreciation_schedule_{from_date}_to_{to_date}.xlsx"
        return send_file(
            excel_file,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        logger.exception("Error downloading depreciation schedule: %s", e)
        return jsonify({"error": "Failed to download depreciation schedule"}), 500


@depreciation_calc_bp.route("/api/calculate", methods=["POST"])
@_login_required
def api_calculate():
    """
    Calculate depreciation for a single asset.

    Request (JSON):
        - asset_value: Current written down value
        - effective_life: Effective life in years
        - method: "diminishing" or "prime_cost"
        - period_months: Period length in months (default 3)

    Returns:
        Calculated depreciation amounts
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    asset_value = data.get("asset_value")
    effective_life = data.get("effective_life")
    method = data.get("method", "diminishing")
    period_months = data.get("period_months", 3)

    if asset_value is None or effective_life is None:
        return jsonify({"error": "asset_value and effective_life are required"}), 400

    try:
        asset_value = float(asset_value)
        effective_life = float(effective_life)
        period_months = int(period_months)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid numeric values"}), 400

    if effective_life <= 0:
        return jsonify({"error": "effective_life must be positive"}), 400

    if method not in ("diminishing", "prime_cost"):
        return jsonify({"error": "method must be 'diminishing' or 'prime_cost'"}), 400

    result = calculate_depreciation(asset_value, effective_life, method, period_months)

    return jsonify({"success": True, "calculation": result})
