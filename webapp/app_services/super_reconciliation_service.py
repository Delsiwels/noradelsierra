"""
Super Guarantee Reconciliation Service

Business logic for reconciling SG liability from payroll against
actual super payments, with email reminder capability.
"""

import logging
import os
import re
from datetime import date, datetime, timedelta
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Current SG rate (11.5% from 1 Jul 2024, 12% from 1 Jul 2025)
SG_RATES = [
    (date(2025, 7, 1), 0.12),
    (date(2024, 7, 1), 0.115),
    (date(2023, 7, 1), 0.11),
    (date(2022, 7, 1), 0.105),
    (date(2021, 7, 1), 0.10),
]

# Australian FY quarters with SG deadlines
QUARTER_MAP = {
    1: {
        "label": "Q1 Jul-Sep",
        "start_month": 7,
        "end_month": 9,
        "deadline_month": 10,
        "deadline_day": 28,
    },
    2: {
        "label": "Q2 Oct-Dec",
        "start_month": 10,
        "end_month": 12,
        "deadline_month": 2,
        "deadline_day": 28,
    },
    3: {
        "label": "Q3 Jan-Mar",
        "start_month": 1,
        "end_month": 3,
        "deadline_month": 4,
        "deadline_day": 28,
    },
    4: {
        "label": "Q4 Apr-Jun",
        "start_month": 4,
        "end_month": 6,
        "deadline_month": 7,
        "deadline_day": 28,
    },
}


def _get_sg_rate(reference_date: date) -> float:
    """Get the applicable SG rate for a given date."""
    for effective_date, rate in SG_RATES:
        if reference_date >= effective_date:
            return rate
    return 0.095  # Fallback for older periods


def _get_sg_quarter_and_deadline(from_date: date, to_date: date) -> dict[str, Any]:
    """
    Determine the SG quarter and deadline from a date range.

    Returns dict with: quarter, label, deadline, sg_rate, year
    """
    mid_date = from_date + (to_date - from_date) / 2
    month = mid_date.month

    if month in (7, 8, 9):
        quarter = 1
        fy_year = mid_date.year
    elif month in (10, 11, 12):
        quarter = 2
        fy_year = mid_date.year
    elif month in (1, 2, 3):
        quarter = 3
        fy_year = mid_date.year
    else:  # 4, 5, 6
        quarter = 4
        fy_year = mid_date.year

    q_info = QUARTER_MAP[quarter]

    # Calculate deadline date
    deadline_year = fy_year
    if quarter == 2:
        deadline_year = fy_year + 1  # Q2 Oct-Dec deadline is Feb next year

    deadline = date(
        deadline_year,
        int(str(q_info["deadline_month"])),
        int(str(q_info["deadline_day"])),
    )
    sg_rate = _get_sg_rate(from_date)

    return {
        "quarter": quarter,
        "label": f"{q_info['label']} {fy_year}",
        "deadline": deadline.isoformat(),
        "deadline_display": deadline.strftime("%d %b %Y"),
        "sg_rate": sg_rate,
        "sg_rate_display": f"{sg_rate * 100:.1f}%",
        "year": fy_year,
    }


def _evaluate_super_result(
    total_liability: float,
    total_paid: float,
    has_late_payments: bool,
    deadline: str,
) -> dict[str, Any]:
    """
    Evaluate the super reconciliation status.

    Returns dict with: status, status_label, status_color, message
    """
    variance = round(total_liability - total_paid, 2)
    today = date.today()
    deadline_date = date.fromisoformat(deadline)
    is_past_deadline = today > deadline_date

    if variance <= 0 and not has_late_payments:
        status = "pass"
        label = "FULLY PAID"
        color = "green"
        message = "All super guarantee obligations have been met on time."
    elif variance <= 0 and has_late_payments:
        status = "warning"
        label = "PAID (LATE)"
        color = "yellow"
        message = (
            "Super was paid in full but some payments were made after the deadline. "
            "Late payments may attract the Superannuation Guarantee Charge (SGC)."
        )
    elif variance > 0 and not is_past_deadline:
        status = "warning"
        label = "UNDERPAID"
        color = "yellow"
        message = (
            f"Outstanding super of ${variance:,.2f}. "
            f"The deadline is {deadline_date.strftime('%d %b %Y')} — ensure payment is made before then."
        )
    else:
        status = "fail"
        label = "UNDERPAID"
        color = "red"
        message = (
            f"Outstanding super of ${variance:,.2f} and the deadline has passed. "
            "The employer may be liable for the Superannuation Guarantee Charge (SGC), "
            "which includes the shortfall, interest (10% p.a.), and an administration fee."
        )

    return {
        "status": status,
        "status_label": label,
        "status_color": color,
        "message": message,
        "variance": variance,
        "is_past_deadline": is_past_deadline,
    }


def _xero_api_request(
    access_token: str,
    tenant_id: str,
    endpoint: str,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Make an authenticated request to the Xero API.

    Returns parsed JSON response or error dict.
    """
    base_url = "https://api.xero.com/api.xro/2.0"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Xero-Tenant-Id": tenant_id,
        "Accept": "application/json",
    }

    url = f"{base_url}/{endpoint}"
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result
    except requests.exceptions.HTTPError as e:
        logger.error("Xero API HTTP error for %s: %s", endpoint, e)
        return {"error": str(e), "status_code": getattr(e.response, "status_code", 500)}
    except requests.exceptions.RequestException as e:
        logger.error("Xero API request error for %s: %s", endpoint, e)
        return {"error": str(e)}


def _xero_payroll_request(
    access_token: str,
    tenant_id: str,
    endpoint: str,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Make an authenticated request to the Xero Payroll AU API."""
    base_url = "https://api.xero.com/payroll.xro/1.0"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Xero-Tenant-Id": tenant_id,
        "Accept": "application/json",
    }

    url = f"{base_url}/{endpoint}"
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result
    except requests.exceptions.HTTPError as e:
        status = getattr(e.response, "status_code", 500)
        if status == 403:
            return {"error": "No payroll access", "status_code": 403}
        logger.error("Xero Payroll API error for %s: %s", endpoint, e)
        return {"error": str(e), "status_code": status}
    except requests.exceptions.RequestException as e:
        logger.error("Xero Payroll API request error for %s: %s", endpoint, e)
        return {"error": str(e)}


def _parse_xero_date(date_str: str) -> date | None:
    """Parse Xero's /Date(...)/ format or ISO date string."""
    if not date_str:
        return None

    # Handle /Date(1234567890000+0000)/ format
    match = re.search(r"/Date\((\d+)", date_str)
    if match:
        timestamp_ms = int(match.group(1))
        return datetime.utcfromtimestamp(timestamp_ms / 1000).date()

    # Handle ISO format
    try:
        return date.fromisoformat(date_str[:10])
    except (ValueError, TypeError):
        return None


def get_employee_super_breakdown(
    access_token: str,
    tenant_id: str,
    from_date: date,
    to_date: date,
    sg_rate: float,
) -> dict[str, Any]:
    """
    Get per-employee super breakdown from payroll data.

    Calls Xero Payroll API to fetch pay runs and payslips for the period,
    then aggregates per-employee super data.

    Returns:
        {
            success: bool,
            has_payroll: bool,
            employees: [{name, gross_earnings, sg_rate, expected_super, payslip_super}],
            total_liability: float,
            total_payslip_super: float,
            error: str | None
        }
    """
    # Check payroll access
    payroll_check = _xero_payroll_request(access_token, tenant_id, "PayRuns")
    if "error" in payroll_check:
        if payroll_check.get("status_code") == 403:
            return {
                "success": True,
                "has_payroll": False,
                "employees": [],
                "total_liability": 0,
                "total_payslip_super": 0,
                "error": None,
            }
        return {
            "success": False,
            "has_payroll": False,
            "employees": [],
            "error": payroll_check["error"],
        }

    # Filter pay runs in date range
    pay_runs = payroll_check.get("PayRuns", [])
    filtered_runs = []
    for pr in pay_runs:
        pr_date = _parse_xero_date(pr.get("PayRunPeriodEndDate", ""))
        if pr_date and from_date <= pr_date <= to_date:
            if pr.get("PayRunStatus") == "POSTED":
                filtered_runs.append(pr)

    if not filtered_runs:
        return {
            "success": True,
            "has_payroll": True,
            "employees": [],
            "total_liability": 0,
            "total_payslip_super": 0,
            "error": None,
        }

    # Aggregate per-employee data from payslips
    employee_data: dict[str, dict[str, Any]] = {}

    for pr in filtered_runs:
        pay_run_id = pr.get("PayRunID")
        if not pay_run_id:
            continue

        detail = _xero_payroll_request(access_token, tenant_id, f"PayRuns/{pay_run_id}")
        if "error" in detail:
            continue

        payslips = detail.get("PayRuns", [{}])[0].get("Payslips", [])
        for slip in payslips:
            emp_id = slip.get("EmployeeID", "unknown")
            emp_name = f"{slip.get('FirstName', '')} {slip.get('LastName', '')}".strip()
            if not emp_name:
                emp_name = emp_id

            gross = float(slip.get("Wages", 0))
            super_amount = float(slip.get("Super", 0))

            if emp_id not in employee_data:
                employee_data[emp_id] = {
                    "employee_id": emp_id,
                    "name": emp_name,
                    "gross_earnings": 0,
                    "payslip_super": 0,
                }

            employee_data[emp_id]["gross_earnings"] += gross
            employee_data[emp_id]["payslip_super"] += super_amount

    # Calculate expected super for each employee
    employees = []
    total_liability = 0
    total_payslip_super = 0

    for emp in employee_data.values():
        expected = round(emp["gross_earnings"] * sg_rate, 2)
        total_liability += expected
        total_payslip_super += emp["payslip_super"]

        employees.append(
            {
                "name": emp["name"],
                "gross_earnings": round(emp["gross_earnings"], 2),
                "sg_rate": sg_rate,
                "expected_super": expected,
                "payslip_super": round(emp["payslip_super"], 2),
            }
        )

    employees.sort(key=lambda e: e["name"])

    return {
        "success": True,
        "has_payroll": True,
        "employees": employees,
        "total_liability": round(total_liability, 2),
        "total_payslip_super": round(total_payslip_super, 2),
        "error": None,
    }


def get_super_payments(
    access_token: str,
    tenant_id: str,
    from_date: date,
    to_date: date,
    deadline: str,
) -> dict[str, Any]:
    """
    Get super payments from bank transactions.

    Looks for SPEND transactions to accounts matching super-related keywords
    from quarter start through the deadline date.

    Returns:
        {
            success: bool,
            payments: [{date, description, account_name, amount, is_late}],
            total_paid: float,
            has_late_payments: bool,
            error: str | None
        }
    """
    # Fetch chart of accounts to find super-related accounts
    accounts_resp = _xero_api_request(access_token, tenant_id, "Accounts")
    if "error" in accounts_resp:
        return {
            "success": False,
            "payments": [],
            "total_paid": 0,
            "has_late_payments": False,
            "error": accounts_resp["error"],
        }

    super_keywords = {"super", "superannuation", "sg ", "super guarantee"}
    super_account_ids = set()
    account_name_map: dict[str, str] = {}

    for acct in accounts_resp.get("Accounts", []):
        acct_name = (acct.get("Name") or "").lower()
        acct_id = acct.get("AccountID", "")
        account_name_map[acct_id] = acct.get("Name", "")

        if any(kw in acct_name for kw in super_keywords):
            super_account_ids.add(acct_id)

    if not super_account_ids:
        return {
            "success": True,
            "payments": [],
            "total_paid": 0,
            "has_late_payments": False,
            "error": None,
        }

    # Fetch bank transactions (SPEND type) from quarter start through deadline
    deadline_date = date.fromisoformat(deadline)
    search_end = deadline_date + timedelta(
        days=90
    )  # Look beyond deadline for late payments

    params = {
        "where": f'Type=="SPEND"&&Date>=DateTime({from_date.year},{from_date.month},{from_date.day})&&Date<=DateTime({search_end.year},{search_end.month},{search_end.day})',
    }

    txn_resp = _xero_api_request(access_token, tenant_id, "BankTransactions", params)
    if "error" in txn_resp:
        return {
            "success": False,
            "payments": [],
            "total_paid": 0,
            "has_late_payments": False,
            "error": txn_resp["error"],
        }

    payments = []
    total_paid: float = 0.0
    has_late_payments = False

    for txn in txn_resp.get("BankTransactions", []):
        # Check if any line item hits a super account
        line_items = txn.get("LineItems", [])
        is_super_txn = False
        for li in line_items:
            if li.get("AccountID") in super_account_ids:
                is_super_txn = True
                break

        if not is_super_txn:
            continue

        txn_date = _parse_xero_date(txn.get("Date", ""))
        if not txn_date:
            continue

        amount = abs(float(txn.get("Total", 0)))
        is_late = txn_date > deadline_date

        if is_late:
            has_late_payments = True

        total_paid += amount
        payments.append(
            {
                "date": txn_date.isoformat(),
                "date_display": txn_date.strftime("%d %b %Y"),
                "description": txn.get("Reference")
                or txn.get("Contact", {}).get("Name", "Super Payment"),
                "account_name": account_name_map.get(
                    line_items[0].get("AccountID", "") if line_items else "",
                    "Superannuation",
                ),
                "amount": round(amount, 2),
                "is_late": is_late,
            }
        )

    payments.sort(key=lambda p: p["date"])

    return {
        "success": True,
        "payments": payments,
        "total_paid": round(total_paid, 2),
        "has_late_payments": has_late_payments,
        "error": None,
    }


def generate_super_reconciliation(
    access_token: str,
    tenant_id: str,
    from_date: date,
    to_date: date,
) -> dict[str, Any]:
    """
    Main entry point: generate a full super guarantee reconciliation.

    Combines quarter/deadline info, employee breakdown, payment data,
    and status evaluation.

    Returns:
        {
            success: bool,
            sg_info: dict,
            summary: dict,
            employees: list,
            payments: list,
            error: str | None
        }
    """
    try:
        # Get quarter and deadline info
        sg_info = _get_sg_quarter_and_deadline(from_date, to_date)

        # Get employee super breakdown
        emp_result = get_employee_super_breakdown(
            access_token, tenant_id, from_date, to_date, sg_info["sg_rate"]
        )
        if not emp_result["success"]:
            return {
                "success": False,
                "sg_info": sg_info,
                "summary": None,
                "employees": [],
                "payments": [],
                "error": emp_result.get("error", "Failed to fetch payroll data"),
            }

        # Get super payments
        pay_result = get_super_payments(
            access_token, tenant_id, from_date, to_date, sg_info["deadline"]
        )
        if not pay_result["success"]:
            return {
                "success": False,
                "sg_info": sg_info,
                "summary": None,
                "employees": emp_result["employees"],
                "payments": [],
                "error": pay_result.get("error", "Failed to fetch payment data"),
            }

        # Evaluate result
        evaluation = _evaluate_super_result(
            total_liability=emp_result["total_liability"],
            total_paid=pay_result["total_paid"],
            has_late_payments=pay_result["has_late_payments"],
            deadline=sg_info["deadline"],
        )

        summary = {
            "total_liability": emp_result["total_liability"],
            "total_payslip_super": emp_result["total_payslip_super"],
            "total_paid": pay_result["total_paid"],
            "has_payroll": emp_result["has_payroll"],
            **evaluation,
        }

        return {
            "success": True,
            "sg_info": sg_info,
            "summary": summary,
            "employees": emp_result["employees"],
            "payments": pay_result["payments"],
            "error": None,
        }

    except Exception as e:
        logger.exception("Error generating super reconciliation: %s", e)
        return {
            "success": False,
            "sg_info": None,
            "summary": None,
            "employees": [],
            "payments": [],
            "error": "An unexpected error occurred during reconciliation.",
        }


def send_super_reminder_email(
    to_email: str,
    quarter_label: str,
    deadline: str,
    total_liability: float,
    total_paid: float,
    variance: float,
    status: str,
    tenant_name: str,
) -> dict[str, Any]:
    """
    Send a super guarantee reminder email via Resend API.

    Returns:
        {
            success: bool,
            email_sent: bool,
            error: str | None
        }
    """
    resend_api_key = os.environ.get("RESEND_API_KEY")
    from_email = os.environ.get("RESEND_FROM_EMAIL", "noreply@finql.com.au")

    if not resend_api_key:
        logger.warning("RESEND_API_KEY not configured, skipping email")
        return {
            "success": False,
            "email_sent": False,
            "error": "Email service not configured",
        }

    # Build status-specific message
    if status == "fail":
        status_message = (
            "URGENT: The SG deadline has passed and super remains unpaid. "
            "The employer may be liable for the Superannuation Guarantee Charge (SGC), "
            "which includes the shortfall amount, interest at 10% p.a., "
            "and a $20 per employee per quarter administration fee. "
            "Please arrange immediate payment and consider lodging an SGC statement with the ATO."
        )
    elif status == "warning":
        status_message = (
            "Super payments are currently behind. Please ensure all outstanding "
            "superannuation is paid by the deadline to avoid the Superannuation Guarantee Charge (SGC)."
        )
    else:
        status_message = "Super payments appear to be up to date. Please verify this matches your records."

    subject = f"Super Guarantee Reminder - {quarter_label} - {tenant_name}"

    body = f"""Hi,

This is a reminder regarding the Super Guarantee obligation for {quarter_label}.

Organisation: {tenant_name}
SG Deadline: {deadline}

Summary:
- Total SG Liability (payroll): ${total_liability:,.2f}
- Total Super Paid: ${total_paid:,.2f}
- Variance: ${variance:,.2f}
- Status: {status.upper()}

{status_message}

Please ensure all superannuation payments are made by the deadline
to avoid the Superannuation Guarantee Charge (SGC).

This report was generated by FinQL.
"""

    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_email,
                "to": [to_email],
                "subject": subject,
                "text": body,
            },
            timeout=15,
        )
        resp.raise_for_status()

        return {
            "success": True,
            "email_sent": True,
            "error": None,
        }

    except requests.exceptions.RequestException as e:
        logger.error("Failed to send super reminder email: %s", e)
        return {
            "success": False,
            "email_sent": False,
            "error": f"Email delivery failed: {e}",
        }
