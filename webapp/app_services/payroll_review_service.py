"""
Payroll Review Service

Core business logic for:
- Pay run comparison (DRAFT vs POSTED)
- Leave flags extraction and balance warnings
- Employee Excel upload parsing and validation
- Employee creation in Xero
"""

import logging
import re
from datetime import datetime
from io import BytesIO
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Xero Payroll AU API base URL
XERO_PAYROLL_AU_URL = "https://api.xero.com/payroll.xro/1.0"

# Australian states for validation
AUSTRALIAN_STATES = {"NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"}


# =============================================================================
# Pay Run Functions
# =============================================================================


def get_pay_runs_by_status(
    access_token: str, tenant_id: str, status: str
) -> list[dict]:
    """
    Fetch pay runs filtered by status (DRAFT or POSTED).

    Args:
        access_token: Xero OAuth access token
        tenant_id: Xero tenant ID
        status: "DRAFT" or "POSTED"

    Returns:
        List of pay run dicts with summary info
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Xero-Tenant-Id": tenant_id,
        "Accept": "application/json",
    }

    try:
        resp = requests.get(
            f"{XERO_PAYROLL_AU_URL}/PayRuns",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        pay_runs = []
        for pr in data.get("PayRuns", []):
            if pr.get("PayRunStatus") == status:
                pay_runs.append(
                    {
                        "pay_run_id": pr.get("PayRunID"),
                        "pay_run_period_start_date": _parse_xero_date(
                            pr.get("PayRunPeriodStartDate")
                        ),
                        "pay_run_period_end_date": _parse_xero_date(
                            pr.get("PayRunPeriodEndDate")
                        ),
                        "payment_date": _parse_xero_date(pr.get("PaymentDate")),
                        "status": pr.get("PayRunStatus"),
                        "wages": float(pr.get("Wages", 0) or 0),
                        "deductions": float(pr.get("Deductions", 0) or 0),
                        "super": float(pr.get("Super", 0) or 0),
                        "tax": float(pr.get("Tax", 0) or 0),
                        "net_pay": float(pr.get("NetPay", 0) or 0),
                    }
                )

        # Sort by payment date descending
        pay_runs.sort(key=lambda x: x.get("payment_date") or "", reverse=True)
        return pay_runs

    except requests.RequestException as e:
        logger.exception("Failed to fetch pay runs: %s", e)
        return []


def get_draft_pay_runs(access_token: str, tenant_id: str) -> list[dict]:
    """Fetch all DRAFT status pay runs."""
    return get_pay_runs_by_status(access_token, tenant_id, "DRAFT")


def get_recent_posted_pay_run(
    access_token: str, tenant_id: str
) -> dict[str, Any] | None:
    """Get the most recent POSTED pay run."""
    posted = get_pay_runs_by_status(access_token, tenant_id, "POSTED")
    return posted[0] if posted else None


def get_pay_run_with_payslips(
    access_token: str, tenant_id: str, pay_run_id: str
) -> dict[str, Any] | None:
    """
    Fetch a pay run with full payslip details.

    Args:
        access_token: Xero OAuth access token
        tenant_id: Xero tenant ID
        pay_run_id: The pay run ID to fetch

    Returns:
        Pay run dict with Payslips array, or None on error
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Xero-Tenant-Id": tenant_id,
        "Accept": "application/json",
    }

    try:
        resp = requests.get(
            f"{XERO_PAYROLL_AU_URL}/PayRuns/{pay_run_id}",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        pay_runs = data.get("PayRuns", [])
        if not pay_runs:
            return None

        pr = pay_runs[0]
        return {
            "pay_run_id": pr.get("PayRunID"),
            "pay_run_period_start_date": _parse_xero_date(
                pr.get("PayRunPeriodStartDate")
            ),
            "pay_run_period_end_date": _parse_xero_date(pr.get("PayRunPeriodEndDate")),
            "payment_date": _parse_xero_date(pr.get("PaymentDate")),
            "status": pr.get("PayRunStatus"),
            "wages": float(pr.get("Wages", 0) or 0),
            "deductions": float(pr.get("Deductions", 0) or 0),
            "super": float(pr.get("Super", 0) or 0),
            "tax": float(pr.get("Tax", 0) or 0),
            "net_pay": float(pr.get("NetPay", 0) or 0),
            "payslips": pr.get("Payslips", []),
        }

    except requests.RequestException as e:
        logger.exception("Failed to fetch pay run %s: %s", pay_run_id, e)
        return None


def compare_pay_runs(
    draft_detail: dict[str, Any], posted_detail: dict[str, Any]
) -> list[dict]:
    """
    Compare payslips between a DRAFT and POSTED pay run.

    Returns a list of employee comparison rows with variance calculations.
    """
    if not draft_detail or not posted_detail:
        return []

    # Build lookup by employee ID for posted payslips
    posted_by_employee: dict[str, dict] = {}
    for ps in posted_detail.get("payslips", []):
        emp_id = ps.get("EmployeeID")
        if emp_id:
            posted_by_employee[emp_id] = ps

    comparison = []
    for ps in draft_detail.get("payslips", []):
        emp_id = ps.get("EmployeeID")
        emp_name = _get_employee_name_from_payslip(ps)

        draft_gross = _calculate_gross_from_payslip(ps)
        draft_super = float(ps.get("SuperannuationLines", [{}])[0].get("Amount", 0))
        if not draft_super and ps.get("SuperannuationLines"):
            draft_super = sum(
                float(sl.get("Amount", 0) or 0)
                for sl in ps.get("SuperannuationLines", [])
            )

        # Get posted values
        posted_ps = posted_by_employee.get(emp_id, {})
        posted_gross = _calculate_gross_from_payslip(posted_ps) if posted_ps else 0.0
        posted_super = 0.0
        if posted_ps:
            posted_super = sum(
                float(sl.get("Amount", 0) or 0)
                for sl in posted_ps.get("SuperannuationLines", [])
            )

        # Calculate variances
        gross_variance = draft_gross - posted_gross
        super_variance = draft_super - posted_super

        gross_variance_pct = 0.0
        if posted_gross > 0:
            gross_variance_pct = round((gross_variance / posted_gross) * 100, 2)

        super_variance_pct = 0.0
        if posted_super > 0:
            super_variance_pct = round((super_variance / posted_super) * 100, 2)

        # Determine flag level
        max_variance_pct = max(abs(gross_variance_pct), abs(super_variance_pct))
        flag = "normal"
        if max_variance_pct > 25:
            flag = "alert"
        elif max_variance_pct > 10:
            flag = "warning"

        comparison.append(
            {
                "employee_id": emp_id,
                "name": emp_name,
                "draft_gross": round(draft_gross, 2),
                "posted_gross": round(posted_gross, 2),
                "gross_variance": round(gross_variance, 2),
                "gross_variance_pct": gross_variance_pct,
                "draft_super": round(draft_super, 2),
                "posted_super": round(posted_super, 2),
                "super_variance": round(super_variance, 2),
                "super_variance_pct": super_variance_pct,
                "flag": flag,
            }
        )

    return comparison


# =============================================================================
# Leave Functions
# =============================================================================


def get_leave_in_payslips(payslips: list[dict]) -> list[dict]:
    """
    Extract leave earnings from payslips.

    Looks for LeaveEarningsLines in each payslip.
    """
    leave_items = []

    for ps in payslips:
        emp_id = ps.get("EmployeeID")
        emp_name = _get_employee_name_from_payslip(ps)

        leave_lines = ps.get("LeaveEarningsLines", [])
        for leave in leave_lines:
            leave_type_id = leave.get("LeaveTypeID")
            leave_items.append(
                {
                    "employee_id": emp_id,
                    "name": emp_name,
                    "leave_type_id": leave_type_id,
                    "leave_type": leave.get("LeaveName", "Leave"),
                    "hours": float(leave.get("NumberOfUnits", 0) or 0),
                    "amount": float(leave.get("Amount", 0) or 0),
                }
            )

    return leave_items


def get_employee_leave_balances(
    access_token: str, tenant_id: str, employee_ids: list[str]
) -> dict[str, list[dict]]:
    """
    Fetch leave balances for a list of employees.

    Returns a dict mapping employee_id -> list of leave balances.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Xero-Tenant-Id": tenant_id,
        "Accept": "application/json",
    }

    balances: dict[str, list[dict]] = {}

    for emp_id in employee_ids:
        try:
            resp = requests.get(
                f"{XERO_PAYROLL_AU_URL}/Employees/{emp_id}",
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            employees = data.get("Employees", [])
            if employees:
                emp = employees[0]
                leave_balances = []
                for lb in emp.get("LeaveBalances", []):
                    leave_balances.append(
                        {
                            "leave_type_id": lb.get("LeaveTypeID"),
                            "leave_name": lb.get("LeaveName", "Leave"),
                            "balance": float(lb.get("NumberOfUnits", 0) or 0),
                        }
                    )
                balances[emp_id] = leave_balances

        except requests.RequestException as e:
            logger.warning("Failed to fetch leave balance for %s: %s", emp_id, e)
            balances[emp_id] = []

    return balances


def build_leave_flags_response(
    payslips: list[dict],
    leave_balances: dict[str, list[dict]],
    low_balance_threshold: float = 40.0,
) -> list[dict]:
    """
    Build the leave flags response combining leave in payslips with balances.

    Flags employees with low remaining balance after the current leave is taken.
    """
    leave_items = get_leave_in_payslips(payslips)
    result = []

    for item in leave_items:
        emp_id = item["employee_id"]
        leave_type_id = item["leave_type_id"]
        hours_taken = item["hours"]

        # Find matching balance
        emp_balances = leave_balances.get(emp_id, [])
        current_balance = None
        for bal in emp_balances:
            if bal["leave_type_id"] == leave_type_id:
                current_balance = bal["balance"]
                break

        balance_remaining = None
        low_balance_warning = False

        if current_balance is not None:
            balance_remaining = current_balance - hours_taken
            if balance_remaining < low_balance_threshold:
                low_balance_warning = True

        result.append(
            {
                "employee_id": emp_id,
                "name": item["name"],
                "leave_type": item["leave_type"],
                "hours": item["hours"],
                "amount": item["amount"],
                "balance_remaining": (
                    round(balance_remaining, 2)
                    if balance_remaining is not None
                    else None
                ),
                "low_balance_warning": low_balance_warning,
            }
        )

    return result


# =============================================================================
# Employee Excel Upload Functions
# =============================================================================

# Required columns in the Excel template
EMPLOYEE_COLUMNS = [
    "First Name",
    "Last Name",
    "Date of Birth",
    "Email",
    "Phone",
    "Address Line 1",
    "City",
    "State",
    "Postcode",
    "Start Date",
    "Job Title",
    "TFN",
    "Bank BSB",
    "Bank Account Number",
    "Bank Account Name",
    "Super Fund USI",
    "Super Member Number",
]

REQUIRED_COLUMNS = [
    "First Name",
    "Last Name",
    "Date of Birth",
    "Email",
    "Start Date",
    "TFN",
    "Bank BSB",
    "Bank Account Number",
    "Bank Account Name",
    "Super Fund USI",
]


def parse_employee_excel(file_data: bytes) -> dict[str, Any]:
    """
    Parse an uploaded Excel file containing employee data.

    Args:
        file_data: Raw bytes of the uploaded Excel file

    Returns:
        Dict with parsed_count, valid_count, and employees list
    """
    try:
        import openpyxl
    except ImportError:
        logger.error("openpyxl not installed")
        return {
            "success": False,
            "error": "Excel parsing library not available",
            "parsed_count": 0,
            "valid_count": 0,
            "employees": [],
        }

    try:
        wb = openpyxl.load_workbook(BytesIO(file_data), read_only=True)
        ws = wb.active

        if ws is None:
            return {
                "success": False,
                "error": "No worksheet found in Excel file",
                "parsed_count": 0,
                "valid_count": 0,
                "employees": [],
            }

        # Read header row
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return {
                "success": False,
                "error": "Excel file is empty",
                "parsed_count": 0,
                "valid_count": 0,
                "employees": [],
            }

        header = [str(h).strip() if h else "" for h in rows[0]]

        # Map column indices
        col_indices = {}
        for i, h in enumerate(header):
            if h in EMPLOYEE_COLUMNS:
                col_indices[h] = i

        employees = []
        for row_num, row in enumerate(rows[1:], start=2):
            if not row or all(c is None or c == "" for c in row):
                continue

            emp = {
                "row": row_num,
                "first_name": _get_cell_value(row, col_indices, "First Name"),
                "last_name": _get_cell_value(row, col_indices, "Last Name"),
                "date_of_birth": _get_cell_value(row, col_indices, "Date of Birth"),
                "email": _get_cell_value(row, col_indices, "Email"),
                "phone": _get_cell_value(row, col_indices, "Phone"),
                "address_line_1": _get_cell_value(row, col_indices, "Address Line 1"),
                "city": _get_cell_value(row, col_indices, "City"),
                "state": _get_cell_value(row, col_indices, "State"),
                "postcode": _get_cell_value(row, col_indices, "Postcode"),
                "start_date": _get_cell_value(row, col_indices, "Start Date"),
                "job_title": _get_cell_value(row, col_indices, "Job Title"),
                "tfn": _get_cell_value(row, col_indices, "TFN"),
                "bank_bsb": _get_cell_value(row, col_indices, "Bank BSB"),
                "bank_account_number": _get_cell_value(
                    row, col_indices, "Bank Account Number"
                ),
                "bank_account_name": _get_cell_value(
                    row, col_indices, "Bank Account Name"
                ),
                "super_fund_usi": _get_cell_value(row, col_indices, "Super Fund USI"),
                "super_member_number": _get_cell_value(
                    row, col_indices, "Super Member Number"
                ),
            }

            # Validate this employee
            validation = validate_employee_data([emp])
            emp["valid"] = validation[0]["valid"]
            emp["errors"] = validation[0]["errors"]

            employees.append(emp)

        valid_count = sum(1 for e in employees if e["valid"])

        return {
            "success": True,
            "parsed_count": len(employees),
            "valid_count": valid_count,
            "employees": employees,
        }

    except Exception as e:
        logger.exception("Error parsing Excel file: %s", e)
        return {
            "success": False,
            "error": f"Failed to parse Excel file: {str(e)}",
            "parsed_count": 0,
            "valid_count": 0,
            "employees": [],
        }


def validate_employee_data(employees: list[dict]) -> list[dict]:
    """
    Validate required fields and formats for employee data.

    Returns the same list with 'valid' and 'errors' fields added.
    """
    result = []

    for emp in employees:
        errors = []

        # Required field checks
        if not emp.get("first_name"):
            errors.append("First Name is required")
        if not emp.get("last_name"):
            errors.append("Last Name is required")
        if not emp.get("email"):
            errors.append("Email is required")
        elif not _is_valid_email(emp.get("email", "")):
            errors.append("Email format is invalid")
        if not emp.get("date_of_birth"):
            errors.append("Date of Birth is required")
        else:
            dob = _parse_date_string(emp.get("date_of_birth"))
            if not dob:
                errors.append("Date of Birth must be in DD/MM/YYYY format")
        if not emp.get("start_date"):
            errors.append("Start Date is required")
        else:
            sd = _parse_date_string(emp.get("start_date"))
            if not sd:
                errors.append("Start Date must be in DD/MM/YYYY format")

        # TFN validation (9 digits)
        tfn = str(emp.get("tfn", "") or "").replace(" ", "")
        if not tfn:
            errors.append("TFN is required")
        elif not re.match(r"^\d{9}$", tfn):
            errors.append("TFN must be 9 digits")

        # BSB validation (6 digits)
        bsb = str(emp.get("bank_bsb", "") or "").replace("-", "").replace(" ", "")
        if not bsb:
            errors.append("Bank BSB is required")
        elif not re.match(r"^\d{6}$", bsb):
            errors.append("Bank BSB must be 6 digits")

        # Bank account number
        if not emp.get("bank_account_number"):
            errors.append("Bank Account Number is required")

        # Bank account name
        if not emp.get("bank_account_name"):
            errors.append("Bank Account Name is required")

        # Super Fund USI
        if not emp.get("super_fund_usi"):
            errors.append("Super Fund USI is required")

        # State validation (if provided)
        state = emp.get("state", "")
        if state and state.upper() not in AUSTRALIAN_STATES:
            errors.append(
                f"State must be one of: {', '.join(sorted(AUSTRALIAN_STATES))}"
            )

        result.append(
            {
                **emp,
                "valid": len(errors) == 0,
                "errors": errors,
            }
        )

    return result


def create_employees_in_xero(
    access_token: str, tenant_id: str, employees: list[dict]
) -> dict[str, Any]:
    """
    Create new employees in Xero Payroll.

    Args:
        access_token: Xero OAuth access token
        tenant_id: Xero tenant ID
        employees: List of validated employee dicts

    Returns:
        Dict with success status and results per employee
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Xero-Tenant-Id": tenant_id,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    results = []
    success_count = 0
    error_count = 0

    for emp in employees:
        if not emp.get("valid", False):
            results.append(
                {
                    "row": emp.get("row"),
                    "name": f"{emp.get('first_name', '')} {emp.get('last_name', '')}",
                    "success": False,
                    "error": "Validation errors: " + "; ".join(emp.get("errors", [])),
                }
            )
            error_count += 1
            continue

        # Build Xero employee payload
        payload = _build_xero_employee_payload(emp)

        try:
            resp = requests.post(
                f"{XERO_PAYROLL_AU_URL}/Employees",
                headers=headers,
                json={"Employees": [payload]},
                timeout=30,
            )

            if resp.status_code in (200, 201):
                data = resp.json()
                created = data.get("Employees", [{}])[0]
                results.append(
                    {
                        "row": emp.get("row"),
                        "name": f"{emp.get('first_name', '')} {emp.get('last_name', '')}",
                        "success": True,
                        "employee_id": created.get("EmployeeID"),
                    }
                )
                success_count += 1
            else:
                error_msg = resp.text[:200] if resp.text else f"HTTP {resp.status_code}"
                results.append(
                    {
                        "row": emp.get("row"),
                        "name": f"{emp.get('first_name', '')} {emp.get('last_name', '')}",
                        "success": False,
                        "error": f"Xero API error: {error_msg}",
                    }
                )
                error_count += 1

        except requests.RequestException as e:
            results.append(
                {
                    "row": emp.get("row"),
                    "name": f"{emp.get('first_name', '')} {emp.get('last_name', '')}",
                    "success": False,
                    "error": f"Request failed: {str(e)}",
                }
            )
            error_count += 1

    return {
        "success": error_count == 0,
        "total": len(employees),
        "created": success_count,
        "failed": error_count,
        "results": results,
    }


def get_super_fund_by_usi(
    access_token: str, tenant_id: str, usi: str
) -> dict[str, Any] | None:
    """
    Look up a regulated super fund by USI.

    Returns fund details or None if not found.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Xero-Tenant-Id": tenant_id,
        "Accept": "application/json",
    }

    try:
        resp = requests.get(
            f"{XERO_PAYROLL_AU_URL}/SuperFundProducts",
            params={"USI": usi},
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        products = data.get("SuperFundProducts", [])
        if products:
            product = products[0]
            return {
                "usi": product.get("USI"),
                "product_name": product.get("ProductName"),
                "abn": product.get("ABN"),
            }
        return None

    except requests.RequestException as e:
        logger.warning("Failed to look up super fund USI %s: %s", usi, e)
        return None


# =============================================================================
# Helper Functions
# =============================================================================


def _parse_xero_date(date_value: str | None) -> str | None:
    """Parse Xero date format /Date(timestamp)/ to ISO string."""
    if not date_value:
        return None

    if "/Date(" in str(date_value):
        try:
            ts = int(
                str(date_value).split("(")[1].split("+")[0].split("-")[0].split(")")[0]
            )
            dt = datetime.fromtimestamp(ts / 1000)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, IndexError):
            return None

    return str(date_value)


def _get_employee_name_from_payslip(payslip: dict) -> str:
    """Extract employee name from payslip."""
    first = payslip.get("FirstName", "")
    last = payslip.get("LastName", "")
    if first or last:
        return f"{first} {last}".strip()
    emp_id = payslip.get("EmployeeID")
    return str(emp_id) if emp_id else "Unknown"


def _calculate_gross_from_payslip(payslip: dict) -> float:
    """Calculate gross pay from earnings lines."""
    gross = 0.0

    # Regular earnings
    for line in payslip.get("EarningsLines", []):
        gross += float(line.get("Amount", 0) or 0)

    # Leave earnings
    for line in payslip.get("LeaveEarningsLines", []):
        gross += float(line.get("Amount", 0) or 0)

    return gross


def _get_cell_value(row: tuple, col_indices: dict, column_name: str) -> str:
    """Safely get a cell value from a row by column name."""
    idx = col_indices.get(column_name)
    if idx is None or idx >= len(row):
        return ""

    value = row[idx]
    if value is None:
        return ""

    # Handle datetime objects from Excel
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")

    return str(value).strip()


def _parse_date_string(date_str: str | None) -> datetime | None:
    """Parse a date string in DD/MM/YYYY or other common formats."""
    if not date_str:
        return None

    date_str = str(date_str).strip()

    formats = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%d/%m/%y",
        "%d-%m-%y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    return None


def _is_valid_email(email: str) -> bool:
    """Basic email validation."""
    if not email:
        return False
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def _build_xero_employee_payload(emp: dict) -> dict:
    """Build the Xero API payload for creating an employee."""
    dob = _parse_date_string(emp.get("date_of_birth"))
    start = _parse_date_string(emp.get("start_date"))

    payload: dict[str, Any] = {
        "FirstName": emp.get("first_name", ""),
        "LastName": emp.get("last_name", ""),
        "Email": emp.get("email", ""),
        "Status": "ACTIVE",
    }

    if dob:
        payload["DateOfBirth"] = f"/Date({int(dob.timestamp() * 1000)})/"

    if start:
        payload["StartDate"] = f"/Date({int(start.timestamp() * 1000)})/"

    if emp.get("phone"):
        payload["Phone"] = emp.get("phone")

    if emp.get("job_title"):
        payload["JobTitle"] = emp.get("job_title")

    # TFN
    tfn = str(emp.get("tfn", "") or "").replace(" ", "")
    if tfn:
        payload["TaxDeclaration"] = {"TaxFileNumber": tfn}

    # Address
    if emp.get("address_line_1"):
        payload["HomeAddress"] = {
            "AddressLine1": emp.get("address_line_1", ""),
            "City": emp.get("city", ""),
            "Region": emp.get("state", ""),
            "PostalCode": emp.get("postcode", ""),
            "Country": "AUSTRALIA",
        }

    # Bank account
    bsb = str(emp.get("bank_bsb", "") or "").replace("-", "").replace(" ", "")
    if bsb:
        payload["BankAccounts"] = [
            {
                "StatementText": emp.get("bank_account_name", "Salary"),
                "AccountName": emp.get("bank_account_name", ""),
                "BSB": bsb,
                "AccountNumber": str(emp.get("bank_account_number", "")),
                "Remainder": True,
            }
        ]

    # Super membership
    if emp.get("super_fund_usi"):
        payload["SuperMemberships"] = [
            {
                "SuperFundID": emp.get("super_fund_usi"),  # Will be resolved by Xero
                "EmployeeNumber": emp.get("super_member_number", ""),
            }
        ]

    return payload
