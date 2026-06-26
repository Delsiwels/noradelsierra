"""
Cash Flow Forecast Blueprint

Page route and REST API endpoints for 12-month cash flow forecasting
with BAS compliance calendar and lodge-method selector.

Endpoints:
- GET  /cash-flow-forecast              - Render forecast page
- GET  /api/forecast/cash-position      - Fetch bank balances from Xero
- POST /api/forecast/generate           - Generate 12-month forecast
- GET  /api/forecast/deadlines          - Get BAS deadlines for lodge method
- PUT  /api/forecast/lodge-method       - Persist lodge preference
"""

import logging

import requests
from flask import Blueprint, current_app, jsonify, render_template, request

from webapp.app_services.forecast_service import (
    fetch_bank_accounts,
    generate_cash_flow_forecast,
)
from webapp.blueprints._helpers import (
    get_current_user as _get_current_user,
)
from webapp.blueprints._helpers import get_xero_credentials
from webapp.blueprints._helpers import (
    login_required as _login_required,
)

logger = logging.getLogger(__name__)

forecast_bp = Blueprint("forecast", __name__)


# =========================================================================
# Page Route
# =========================================================================


@forecast_bp.route("/cash-flow-forecast")
@_login_required
def cash_flow_forecast_page():
    """Render the cash flow forecast page."""
    user = _get_current_user()
    lodge_method = "self"
    if user:
        lodge_method = getattr(user, "bas_lodge_method", "self") or "self"
    return render_template(
        "cash_flow_forecast.html",
        lodge_method=lodge_method,
    )


# =========================================================================
# API Routes
# =========================================================================


@forecast_bp.route("/api/forecast/cash-position", methods=["GET"])
@_login_required
def api_cash_position():
    """
    Fetch current bank account balances from Xero.

    Requires an active Xero session (access_token + tenant_id in session).

    Response:
        - accounts: list of {name, balance, id}
        - total_cash: float
    """
    access_token, tenant_id = get_xero_credentials()

    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    try:
        accounts, total_cash = fetch_bank_accounts(access_token, tenant_id)
        return jsonify(
            {
                "accounts": accounts,
                "total_cash": round(total_cash, 2),
            }
        )
    except requests.RequestException as e:
        logger.exception("Xero API error fetching bank accounts: %s", e)
        return jsonify({"error": "Failed to fetch bank accounts from Xero"}), 502


@forecast_bp.route("/api/forecast/generate", methods=["POST"])
@_login_required
def api_generate_forecast():
    """
    Generate a 12-month cash flow forecast.

    Reads Xero session for access_token + tenant_id.
    Fetches bank accounts, last 6 months of transactions,
    computes averages, and projects 12 months forward with
    BAS deadline overlays.

    Request (JSON, optional):
        - lodge_method: "self" or "agent" (default: from user preference)

    Response:
        - accounts: list of bank accounts with balances
        - total_cash: current total cash
        - months: list of 12 forecast month objects
        - risk_indicators: list of risk alert objects
        - deadlines: list of BAS deadline objects
    """
    access_token, tenant_id = get_xero_credentials()

    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    user = _get_current_user()
    body = request.get_json(silent=True) or {}
    lodge_method = body.get("lodge_method")
    if not lodge_method and user:
        lodge_method = getattr(user, "bas_lodge_method", "self") or "self"
    if lodge_method not in ("self", "agent"):
        lodge_method = "self"

    try:
        return jsonify(
            generate_cash_flow_forecast(access_token, tenant_id, lodge_method)
        )
    except requests.RequestException as e:
        logger.exception("Xero API error generating forecast: %s", e)
        return jsonify({"error": "Failed to fetch data from Xero"}), 502
    except Exception as e:
        logger.exception("Error generating forecast: %s", e)
        return jsonify({"error": "Failed to generate forecast"}), 500


@forecast_bp.route("/api/forecast/deadlines", methods=["GET"])
@_login_required
def api_forecast_deadlines():
    """
    Get BAS deadlines for a given lodge method.

    Query params:
        - lodge_method: "self" or "agent" (default: user preference or "self")

    Response:
        - deadlines: list of deadline objects
        - lodge_method: the method used
    """
    user = _get_current_user()
    lodge_method = request.args.get("lodge_method")
    if not lodge_method and user:
        lodge_method = getattr(user, "bas_lodge_method", "self") or "self"
    if lodge_method not in ("self", "agent"):
        lodge_method = "self"

    from webapp.services.bas_deadlines import get_deadlines_for_forecast

    deadlines = get_deadlines_for_forecast(
        frequency="quarterly",
        lodge_method=lodge_method,
        months_ahead=12,
    )

    deadlines_json = []
    for dl in deadlines:
        deadlines_json.append(
            {
                "quarter": dl.get("quarter", ""),
                "due_date": dl["due_date_str"],
                "due_date_iso": dl["due_date"].isoformat(),
                "days_remaining": dl["days_remaining"],
                "status": dl.get("status", ""),
            }
        )

    return jsonify({"deadlines": deadlines_json, "lodge_method": lodge_method})


@forecast_bp.route("/api/forecast/lodge-method", methods=["PUT"])
@_login_required
def api_set_lodge_method():
    """
    Persist the user's BAS lodge method preference.

    Request (JSON):
        - lodge_method: "self" or "agent"

    Response:
        - lodge_method: the saved value
    """
    data = request.get_json(silent=True) or {}
    lodge_method = data.get("lodge_method", "")

    if lodge_method not in ("self", "agent"):
        return jsonify({"error": "lodge_method must be 'self' or 'agent'"}), 400

    user = _get_current_user()
    if not user:
        if current_app.config.get("TESTING"):
            # In testing mode, persist to the most recent user
            from webapp.models import User, db

            test_user = User.query.first()
            if test_user:
                test_user.bas_lodge_method = lodge_method
                db.session.commit()
            return jsonify({"lodge_method": lodge_method})
        return jsonify({"error": "Authentication required"}), 401

    from webapp.models import db

    user.bas_lodge_method = lodge_method
    db.session.commit()

    return jsonify({"lodge_method": lodge_method})
