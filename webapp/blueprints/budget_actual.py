"""
Budget vs Actual Report Blueprint

Routes for budget vs actual comparison.

Endpoints:
- GET  /budget-actual/              - Render main page
- GET  /budget-actual/api/generate  - Generate comparison
- GET  /budget-actual/api/download  - Export to Excel
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

from webapp.app_services.budget_actual_service import (
    export_to_excel,
    generate_budget_vs_actual,
)

logger = logging.getLogger(__name__)

budget_actual_bp = Blueprint("budget_actual", __name__, url_prefix="/budget-actual")


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


@budget_actual_bp.route("/")
@_login_required
def index():
    return render_template("budget_actual.html")


@budget_actual_bp.route("/api/generate", methods=["GET"])
@_login_required
def api_generate():
    access_token, tenant_id = _get_xero_credentials()
    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    if not from_date or not to_date:
        return jsonify({"error": "from_date and to_date are required"}), 400

    try:
        result = generate_budget_vs_actual(access_token, tenant_id, from_date, to_date)
        return jsonify(result)
    except Exception as e:
        logger.exception("Error generating budget vs actual: %s", e)
        return jsonify({"error": "Failed to generate report"}), 500


@budget_actual_bp.route("/api/download", methods=["GET"])
@_login_required
def api_download():
    access_token, tenant_id = _get_xero_credentials()
    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    if not from_date or not to_date:
        return jsonify({"error": "from_date and to_date are required"}), 400

    try:
        result = generate_budget_vs_actual(access_token, tenant_id, from_date, to_date)
        if not result.get("success"):
            return jsonify({"error": result.get("error", "Failed")}), 500

        excel_file = export_to_excel(result)
        filename = f"budget_vs_actual_{from_date}_to_{to_date}.xlsx"
        return send_file(
            excel_file,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        logger.exception("Error downloading budget vs actual: %s", e)
        return jsonify({"error": "Failed to download"}), 500
