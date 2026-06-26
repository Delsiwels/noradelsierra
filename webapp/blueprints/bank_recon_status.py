"""
Bank Reconciliation Status Blueprint

Routes for bank account reconciliation status dashboard.

Endpoints:
- GET  /bank-recon-status/              - Render main page
- GET  /bank-recon-status/api/generate  - Generate reconciliation status
- GET  /bank-recon-status/api/download  - Export to Excel
"""

import logging

from flask import (
    Blueprint,
    jsonify,
    render_template,
    request,
    send_file,
)

from webapp.app_services.bank_recon_status_service import (
    export_to_excel,
    generate_bank_recon_status,
)
from webapp.blueprints._helpers import (
    get_xero_credentials as _get_xero_credentials,
)
from webapp.blueprints._helpers import (
    login_required as _login_required,
)

logger = logging.getLogger(__name__)

bank_recon_status_bp = Blueprint(
    "bank_recon_status", __name__, url_prefix="/bank-recon-status"
)


# =============================================================================
# Page Route
# =============================================================================


@bank_recon_status_bp.route("/")
@_login_required
def index():
    """Render the bank reconciliation status page."""
    return render_template("bank_recon_status.html")


# =============================================================================
# API Routes
# =============================================================================


@bank_recon_status_bp.route("/api/generate", methods=["GET"])
@_login_required
def api_generate():
    """
    Generate bank reconciliation status data.

    Query params:
        - as_at_date: Date for status check (YYYY-MM-DD)

    Returns:
        Bank account status with unreconciled transactions
    """
    access_token, tenant_id = _get_xero_credentials()

    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    as_at_date = request.args.get("as_at_date")

    if not as_at_date:
        return jsonify({"error": "as_at_date is required"}), 400

    try:
        result = generate_bank_recon_status(access_token, tenant_id, as_at_date)
        return jsonify(result)
    except Exception as e:
        logger.exception("Error generating bank recon status: %s", e)
        return jsonify({"error": "Failed to generate bank reconciliation status"}), 500


@bank_recon_status_bp.route("/api/download", methods=["GET"])
@_login_required
def api_download():
    """
    Download bank reconciliation status as Excel.

    Query params:
        - as_at_date: Date for status check (YYYY-MM-DD)

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
        result = generate_bank_recon_status(access_token, tenant_id, as_at_date)

        if not result.get("success"):
            return jsonify({"error": result.get("error", "Generation failed")}), 500

        excel_file = export_to_excel(result)

        filename = f"bank_recon_status_{as_at_date}.xlsx"
        return send_file(
            excel_file,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        logger.exception("Error downloading bank recon status: %s", e)
        return jsonify({"error": "Failed to download bank reconciliation status"}), 500
