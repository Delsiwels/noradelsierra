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
from datetime import UTC, date, datetime, timedelta
from functools import wraps

import requests
from flask import Blueprint, current_app, jsonify, render_template, request, session

logger = logging.getLogger(__name__)

forecast_bp = Blueprint("forecast", __name__)


def _get_current_user():
    """Get current authenticated user."""
    if current_app.config.get("TESTING"):
        return None
    try:
        from flask_login import current_user

        if current_user.is_authenticated:
            return current_user
    except (ImportError, AttributeError):
        pass
    return None


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
    access_token = session.get("xero_access_token")
    tenant_id = session.get("xero_tenant_id")

    if not access_token or not tenant_id:
        return jsonify({"error": "Xero not connected"}), 400

    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Xero-Tenant-Id": tenant_id,
            "Accept": "application/json",
        }
        resp = requests.get(
            "https://api.xero.com/api.xro/2.0/Accounts",
            params={"where": 'Type=="BANK"'},
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        accounts = []
        total_cash = 0.0
        for acct in data.get("Accounts", []):
            balance = float(acct.get("BankAccountBalance", 0) or 0)
            accounts.append(
                {
                    "name": acct.get("Name", "Unknown"),
                    "balance": round(balance, 2),
                    "id": acct.get("AccountID", ""),
                }
            )
            total_cash += balance

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
    access_token = session.get("xero_access_token")
    tenant_id = session.get("xero_tenant_id")

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
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Xero-Tenant-Id": tenant_id,
            "Accept": "application/json",
        }

        # 1. Fetch bank accounts
        acct_resp = requests.get(
            "https://api.xero.com/api.xro/2.0/Accounts",
            params={"where": 'Type=="BANK"'},
            headers=headers,
            timeout=15,
        )
        acct_resp.raise_for_status()
        acct_data = acct_resp.json()

        accounts = []
        total_cash = 0.0
        for acct in acct_data.get("Accounts", []):
            balance = float(acct.get("BankAccountBalance", 0) or 0)
            accounts.append(
                {
                    "name": acct.get("Name", "Unknown"),
                    "balance": round(balance, 2),
                    "id": acct.get("AccountID", ""),
                }
            )
            total_cash += balance

        # 2. Fetch last 6 months of bank transactions
        six_months_ago = (datetime.now(UTC) - timedelta(days=183)).strftime("%Y-%m-%d")
        txn_resp = requests.get(
            "https://api.xero.com/api.xro/2.0/BankTransactions",
            params={"where": f'Date>=DateTime({six_months_ago.replace("-", ",")})'},
            headers=headers,
            timeout=30,
        )
        txn_resp.raise_for_status()
        txn_data = txn_resp.json()

        # 3. Compute monthly avg inflows/outflows
        monthly_inflows: dict[str, float] = {}
        monthly_outflows: dict[str, float] = {}

        for txn in txn_data.get("BankTransactions", []):
            amount = float(txn.get("Total", 0) or 0)
            txn_type = txn.get("Type", "")
            txn_date = txn.get("Date", "")

            # Parse Xero date format /Date(timestamp)/
            if "/Date(" in txn_date:
                ts = int(txn_date.split("(")[1].split("+")[0].split(")")[0])
                dt = datetime.fromtimestamp(ts / 1000, tz=UTC)
            else:
                try:
                    dt = datetime.fromisoformat(txn_date)
                except (ValueError, TypeError):
                    continue

            month_key = dt.strftime("%Y-%m")

            if txn_type == "RECEIVE":
                monthly_inflows[month_key] = monthly_inflows.get(month_key, 0) + amount
            elif txn_type == "SPEND":
                monthly_outflows[month_key] = (
                    monthly_outflows.get(month_key, 0) + amount
                )

        # Calculate averages
        num_months = max(
            len(set(list(monthly_inflows.keys()) + list(monthly_outflows.keys()))), 1
        )
        avg_inflow = round(sum(monthly_inflows.values()) / num_months, 2)
        avg_outflow = round(sum(monthly_outflows.values()) / num_months, 2)

        # 4. Get BAS deadlines for the forecast period
        from webapp.services.bas_deadlines import get_deadlines_for_forecast

        deadlines = get_deadlines_for_forecast(
            frequency="quarterly",
            lodge_method=lodge_method,
            months_ahead=12,
        )

        # Build a map of due_date -> deadline info for overlay
        deadline_by_month: dict[str, dict] = {}
        for dl in deadlines:
            due = dl["due_date"]
            month_key = due.strftime("%Y-%m")
            deadline_by_month[month_key] = {
                "quarter": dl.get("quarter", ""),
                "due_date": dl["due_date_str"],
                "days_remaining": dl["days_remaining"],
                "estimated_amount": round(avg_outflow * 0.25, 2),
            }

        # 5. Project 12 months forward
        today = date.today()
        months = []
        running_balance = round(total_cash, 2)
        lowest_balance = running_balance
        lowest_balance_month = today.strftime("%b %Y")
        bas_payment_count = 0

        for i in range(12):
            if today.month + i <= 12:
                forecast_year = today.year
                forecast_month = today.month + i
            else:
                forecast_year = today.year + (today.month + i - 1) // 12
                forecast_month = (today.month + i - 1) % 12 + 1

            month_key = f"{forecast_year}-{forecast_month:02d}"
            month_label = date(forecast_year, forecast_month, 1).strftime("%b %Y")

            bas_payment = 0.0
            bas_info = None
            if month_key in deadline_by_month:
                bas_payment = deadline_by_month[month_key]["estimated_amount"]
                bas_info = deadline_by_month[month_key]
                bas_payment_count += 1

            net = round(avg_inflow - avg_outflow - bas_payment, 2)
            running_balance = round(running_balance + net, 2)

            if running_balance < lowest_balance:
                lowest_balance = running_balance
                lowest_balance_month = month_label

            months.append(
                {
                    "month": month_label,
                    "month_key": month_key,
                    "inflows": avg_inflow,
                    "outflows": round(-avg_outflow, 2),
                    "bas_payment": round(-bas_payment, 2) if bas_payment else 0,
                    "bas_info": bas_info,
                    "net": net,
                    "balance": running_balance,
                }
            )

        # 6. Compute risk indicators
        risk_indicators = []
        cash_runway = 0
        monthly_burn = avg_outflow - avg_inflow
        if monthly_burn > 0 and total_cash > 0:
            cash_runway = int(total_cash / monthly_burn)

        for m in months:
            if m["balance"] < 0:
                risk_indicators.append(
                    {
                        "level": "red",
                        "message": (
                            f"Projected negative balance of "
                            f"-${abs(m['balance']):,.0f} in {m['month']}"
                        ),
                    }
                )
                break

        if 0 < cash_runway <= 3:
            risk_indicators.append(
                {
                    "level": "yellow",
                    "message": f"Cash runway is only {cash_runway} months",
                }
            )

        for m in months:
            if m["bas_info"]:
                risk_indicators.append(
                    {
                        "level": "blue",
                        "message": (
                            f"{m['bas_info']['quarter']} BAS payment in "
                            f"{m['month']} will reduce balance to "
                            f"${m['balance']:,.0f}"
                        ),
                    }
                )

        # Serialise deadlines for JSON
        deadlines_json = []
        for dl in deadlines:
            deadlines_json.append(
                {
                    "quarter": dl.get("quarter", ""),
                    "due_date": dl["due_date_str"],
                    "days_remaining": dl["days_remaining"],
                    "status": dl.get("status", ""),
                }
            )

        return jsonify(
            {
                "accounts": accounts,
                "total_cash": round(total_cash, 2),
                "months": months,
                "risk_indicators": risk_indicators,
                "deadlines": deadlines_json,
                "summary": {
                    "current_cash": round(total_cash, 2),
                    "cash_runway": cash_runway if monthly_burn > 0 else None,
                    "lowest_balance": round(lowest_balance, 2),
                    "lowest_balance_month": lowest_balance_month,
                    "bas_payments_due": bas_payment_count,
                    "avg_monthly_inflow": avg_inflow,
                    "avg_monthly_outflow": avg_outflow,
                },
            }
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
