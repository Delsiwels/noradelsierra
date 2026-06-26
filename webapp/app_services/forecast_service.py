"""Cash flow forecast business logic.

Pure service layer: fetches Xero bank data and projects a 12-month cash flow
forecast with BAS deadline overlays. HTTP/session concerns stay in the forecast
blueprint; this module takes explicit Xero credentials and returns plain dicts.
"""

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

import requests

from webapp.app_services.xero_http import xero_headers

logger = logging.getLogger(__name__)

XERO_API_BASE = "https://api.xero.com/api.xro/2.0"


def fetch_bank_accounts(access_token: str, tenant_id: str) -> tuple[list[dict], float]:
    """Fetch bank accounts and total cash from Xero.

    Returns ``(accounts, total_cash)``. Raises ``requests.RequestException`` on
    a Xero API error (callers translate this into an HTTP response).
    """
    headers = xero_headers(access_token, tenant_id)
    resp = requests.get(
        f"{XERO_API_BASE}/Accounts",
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
    return accounts, total_cash


def generate_cash_flow_forecast(
    access_token: str, tenant_id: str, lodge_method: str
) -> dict:
    """Generate the 12-month cash flow forecast payload.

    Fetches bank accounts and the last 6 months of transactions, computes
    average monthly inflows/outflows, projects 12 months forward with BAS
    deadline overlays, and derives risk indicators.
    """
    headers = xero_headers(access_token, tenant_id)

    # 1. Fetch bank accounts
    accounts, total_cash = fetch_bank_accounts(access_token, tenant_id)

    # 2. Fetch last 6 months of bank transactions
    six_months_ago = (datetime.now(UTC) - timedelta(days=183)).strftime("%Y-%m-%d")
    txn_resp = requests.get(
        f"{XERO_API_BASE}/BankTransactions",
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
            monthly_outflows[month_key] = monthly_outflows.get(month_key, 0) + amount

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
    months: list[dict[str, Any]] = []
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

    return {
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
