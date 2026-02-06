"""
Prepayment Tracker Blueprint

Routes for prepaid expense tracking.

Endpoints:
- GET  /prepayment-tracker/              - Render main page
- GET  /prepayment-tracker/api/generate  - Generate prepayment schedule
- GET  /prepayment-tracker/api/download  - Export to Excel
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

from webapp.app_services.prepayment_tracker_service import (
    export_to_excel,
    generate_prepayment_schedule,
)

logger = logging.getLogger(__name__)

prepayment_tracker_bp = Blueprint(
    "prepayment_tracker", __name__, url_prefix="/prepayment-tracker"
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


@prepayment_tracker_bp.route("/")
@_login_required
def index():
    return render_template("prepayment_tracker.html")


@prepayment_tracker_bp.route("/api/generate", methods=["GET"])
@_login_required
def api_generate():
    access_token, tenant_id = _get_xero_credentials()
    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    as_at_date = request.args.get("as_at_date")
    if not as_at_date:
        return jsonify({"error": "as_at_date is required"}), 400

    try:
        result = generate_prepayment_schedule(access_token, tenant_id, as_at_date)
        return jsonify(result)
    except Exception as e:
        logger.exception("Error generating prepayment schedule: %s", e)
        return jsonify({"error": "Failed to generate schedule"}), 500


@prepayment_tracker_bp.route("/api/download", methods=["GET"])
@_login_required
def api_download():
    access_token, tenant_id = _get_xero_credentials()
    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    as_at_date = request.args.get("as_at_date")
    if not as_at_date:
        return jsonify({"error": "as_at_date is required"}), 400

    try:
        result = generate_prepayment_schedule(access_token, tenant_id, as_at_date)
        if not result.get("success"):
            return jsonify({"error": result.get("error", "Failed")}), 500

        excel_file = export_to_excel(result)
        filename = f"prepayment_tracker_{as_at_date}.xlsx"
        return send_file(
            excel_file,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        logger.exception("Error downloading prepayment tracker: %s", e)
        return jsonify({"error": "Failed to download"}), 500
