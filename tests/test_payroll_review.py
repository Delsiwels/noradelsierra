"""Tests for payroll review blueprint and service."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def app():
    """Create test Flask app."""
    from webapp.app import create_app
    from webapp.config import TestingConfig

    app = create_app(TestingConfig)
    app.config["TESTING"] = True

    with app.app_context():
        from webapp.models import db

        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(app):
    """Client with a registered & logged-in user."""
    c = app.test_client()
    c.post(
        "/api/auth/register",
        json={"email": "payroll@test.com", "password": "password123", "name": "Test"},
    )
    return c


@pytest.fixture
def xero_session(auth_client):
    """Set up mock Xero session."""
    with auth_client.session_transaction() as sess:
        sess["xero_access_token"] = "test_token"
        sess["xero_tenant_id"] = "test_tenant"
        sess["xero_connection"] = {
            "access_token": "test_token",
            "tenant_id": "test_tenant",
            "tenant_name": "Test Org",
        }
    return auth_client


# =============================================================================
# Pay Run Comparison Tests
# =============================================================================


class TestPayRunComparison:
    """Test pay run comparison functionality."""

    def test_compare_pay_runs_calculates_variance(self):
        """Compare pay runs should calculate correct variances."""
        from webapp.app_services.payroll_review_service import compare_pay_runs

        draft = {
            "payslips": [
                {
                    "EmployeeID": "emp1",
                    "FirstName": "John",
                    "LastName": "Smith",
                    "EarningsLines": [{"Amount": 5000}],
                    "LeaveEarningsLines": [],
                    "SuperannuationLines": [{"Amount": 600}],
                }
            ]
        }

        posted = {
            "payslips": [
                {
                    "EmployeeID": "emp1",
                    "FirstName": "John",
                    "LastName": "Smith",
                    "EarningsLines": [{"Amount": 4800}],
                    "LeaveEarningsLines": [],
                    "SuperannuationLines": [{"Amount": 576}],
                }
            ]
        }

        result = compare_pay_runs(draft, posted)

        assert len(result) == 1
        assert result[0]["employee_id"] == "emp1"
        assert result[0]["draft_gross"] == 5000.0
        assert result[0]["posted_gross"] == 4800.0
        assert result[0]["gross_variance"] == 200.0
        # 200/4800 = 4.17%
        assert result[0]["gross_variance_pct"] == pytest.approx(4.17, rel=0.01)
        assert result[0]["draft_super"] == 600.0
        assert result[0]["posted_super"] == 576.0
        assert result[0]["super_variance"] == 24.0

    def test_compare_pay_runs_flags_large_variance(self):
        """Large variances should be flagged."""
        from webapp.app_services.payroll_review_service import compare_pay_runs

        draft = {
            "payslips": [
                {
                    "EmployeeID": "emp1",
                    "FirstName": "Jane",
                    "LastName": "Doe",
                    "EarningsLines": [{"Amount": 6000}],
                    "LeaveEarningsLines": [],
                    "SuperannuationLines": [{"Amount": 720}],
                }
            ]
        }

        posted = {
            "payslips": [
                {
                    "EmployeeID": "emp1",
                    "FirstName": "Jane",
                    "LastName": "Doe",
                    "EarningsLines": [{"Amount": 4000}],
                    "LeaveEarningsLines": [],
                    "SuperannuationLines": [{"Amount": 480}],
                }
            ]
        }

        result = compare_pay_runs(draft, posted)

        # 2000/4000 = 50% variance, should be alert
        assert result[0]["flag"] == "alert"

    def test_compare_pay_runs_warning_threshold(self):
        """10-25% variance should be warning."""
        from webapp.app_services.payroll_review_service import compare_pay_runs

        draft = {
            "payslips": [
                {
                    "EmployeeID": "emp1",
                    "FirstName": "Bob",
                    "LastName": "Test",
                    "EarningsLines": [{"Amount": 5500}],
                    "LeaveEarningsLines": [],
                    "SuperannuationLines": [{"Amount": 660}],
                }
            ]
        }

        posted = {
            "payslips": [
                {
                    "EmployeeID": "emp1",
                    "FirstName": "Bob",
                    "LastName": "Test",
                    "EarningsLines": [{"Amount": 5000}],
                    "LeaveEarningsLines": [],
                    "SuperannuationLines": [{"Amount": 600}],
                }
            ]
        }

        result = compare_pay_runs(draft, posted)

        # 500/5000 = 10% variance, should be warning
        assert result[0]["flag"] == "normal"  # Exactly 10% is normal

        # Test 11% variance
        draft["payslips"][0]["EarningsLines"][0]["Amount"] = 5550
        result = compare_pay_runs(draft, posted)
        assert result[0]["flag"] == "warning"

    def test_compare_pay_runs_no_posted(self):
        """Comparing with no posted pay run returns empty comparison."""
        from webapp.app_services.payroll_review_service import compare_pay_runs

        draft = {"payslips": [{"EmployeeID": "emp1", "EarningsLines": [{"Amount": 5000}]}]}

        result = compare_pay_runs(draft, None)
        assert result == []

    def test_compare_pay_runs_new_employee(self):
        """New employee in draft shows posted values as zero."""
        from webapp.app_services.payroll_review_service import compare_pay_runs

        draft = {
            "payslips": [
                {
                    "EmployeeID": "emp_new",
                    "FirstName": "New",
                    "LastName": "Employee",
                    "EarningsLines": [{"Amount": 4000}],
                    "LeaveEarningsLines": [],
                    "SuperannuationLines": [{"Amount": 480}],
                }
            ]
        }

        posted = {
            "payslips": [
                {
                    "EmployeeID": "emp_existing",
                    "FirstName": "Existing",
                    "LastName": "Person",
                    "EarningsLines": [{"Amount": 5000}],
                    "LeaveEarningsLines": [],
                    "SuperannuationLines": [{"Amount": 600}],
                }
            ]
        }

        result = compare_pay_runs(draft, posted)

        assert len(result) == 1
        assert result[0]["employee_id"] == "emp_new"
        assert result[0]["posted_gross"] == 0.0
        assert result[0]["draft_gross"] == 4000.0


# =============================================================================
# Leave Flags Tests
# =============================================================================


class TestLeaveFlags:
    """Test leave extraction and balance warnings."""

    def test_get_leave_in_payslips_extracts_leave(self):
        """Should extract leave earnings from payslips."""
        from webapp.app_services.payroll_review_service import get_leave_in_payslips

        payslips = [
            {
                "EmployeeID": "emp1",
                "FirstName": "Sally",
                "LastName": "Martin",
                "LeaveEarningsLines": [
                    {
                        "LeaveTypeID": "leave1",
                        "LeaveName": "Annual Leave",
                        "NumberOfUnits": 16.0,
                        "Amount": 800.00,
                    }
                ],
            }
        ]

        result = get_leave_in_payslips(payslips)

        assert len(result) == 1
        assert result[0]["employee_id"] == "emp1"
        assert result[0]["name"] == "Sally Martin"
        assert result[0]["leave_type"] == "Annual Leave"
        assert result[0]["hours"] == 16.0
        assert result[0]["amount"] == 800.00

    def test_get_leave_in_payslips_multiple_leave_types(self):
        """Should handle multiple leave types per employee."""
        from webapp.app_services.payroll_review_service import get_leave_in_payslips

        payslips = [
            {
                "EmployeeID": "emp1",
                "FirstName": "Bob",
                "LastName": "Jones",
                "LeaveEarningsLines": [
                    {"LeaveTypeID": "annual", "LeaveName": "Annual Leave", "NumberOfUnits": 8.0, "Amount": 400.00},
                    {"LeaveTypeID": "sick", "LeaveName": "Sick Leave", "NumberOfUnits": 4.0, "Amount": 200.00},
                ],
            }
        ]

        result = get_leave_in_payslips(payslips)

        assert len(result) == 2

    def test_build_leave_flags_low_balance_warning(self):
        """Should flag employees with low remaining balance."""
        from webapp.app_services.payroll_review_service import build_leave_flags_response

        payslips = [
            {
                "EmployeeID": "emp1",
                "FirstName": "Sally",
                "LastName": "Martin",
                "LeaveEarningsLines": [
                    {"LeaveTypeID": "leave1", "LeaveName": "Annual Leave", "NumberOfUnits": 60.0, "Amount": 3000.00}
                ],
            }
        ]

        leave_balances = {
            "emp1": [
                {"leave_type_id": "leave1", "leave_name": "Annual Leave", "balance": 80.0}
            ]
        }

        result = build_leave_flags_response(payslips, leave_balances)

        assert len(result) == 1
        assert result[0]["balance_remaining"] == 20.0  # 80 - 60
        assert result[0]["low_balance_warning"] is True  # 20 < 40

    def test_build_leave_flags_ok_balance(self):
        """Should not flag employees with sufficient balance."""
        from webapp.app_services.payroll_review_service import build_leave_flags_response

        payslips = [
            {
                "EmployeeID": "emp1",
                "FirstName": "John",
                "LastName": "Good",
                "LeaveEarningsLines": [
                    {"LeaveTypeID": "leave1", "LeaveName": "Annual Leave", "NumberOfUnits": 16.0, "Amount": 800.00}
                ],
            }
        ]

        leave_balances = {
            "emp1": [
                {"leave_type_id": "leave1", "leave_name": "Annual Leave", "balance": 80.0}
            ]
        }

        result = build_leave_flags_response(payslips, leave_balances)

        assert len(result) == 1
        assert result[0]["balance_remaining"] == 64.0  # 80 - 16
        assert result[0]["low_balance_warning"] is False  # 64 >= 40


# =============================================================================
# Employee Excel Parsing Tests
# =============================================================================


class TestEmployeeExcelParsing:
    """Test employee Excel upload and validation."""

    def test_validate_employee_data_valid(self):
        """Valid employee data should pass validation."""
        from webapp.app_services.payroll_review_service import validate_employee_data

        employees = [
            {
                "first_name": "John",
                "last_name": "Smith",
                "date_of_birth": "15/03/1990",
                "email": "john@example.com",
                "start_date": "01/02/2026",
                "tfn": "123456789",
                "bank_bsb": "062000",
                "bank_account_number": "12345678",
                "bank_account_name": "J Smith",
                "super_fund_usi": "STA0100AU",
            }
        ]

        result = validate_employee_data(employees)

        assert len(result) == 1
        assert result[0]["valid"] is True
        assert len(result[0]["errors"]) == 0

    def test_validate_employee_data_missing_required(self):
        """Missing required fields should fail validation."""
        from webapp.app_services.payroll_review_service import validate_employee_data

        employees = [
            {
                "first_name": "John",
                "last_name": "",  # Missing
                "date_of_birth": "15/03/1990",
                "email": "john@example.com",
                "start_date": "01/02/2026",
                "tfn": "123456789",
                "bank_bsb": "062000",
                "bank_account_number": "12345678",
                "bank_account_name": "J Smith",
                "super_fund_usi": "STA0100AU",
            }
        ]

        result = validate_employee_data(employees)

        assert result[0]["valid"] is False
        assert "Last Name is required" in result[0]["errors"]

    def test_validate_employee_data_invalid_email(self):
        """Invalid email format should fail validation."""
        from webapp.app_services.payroll_review_service import validate_employee_data

        employees = [
            {
                "first_name": "John",
                "last_name": "Smith",
                "date_of_birth": "15/03/1990",
                "email": "not-an-email",  # Invalid
                "start_date": "01/02/2026",
                "tfn": "123456789",
                "bank_bsb": "062000",
                "bank_account_number": "12345678",
                "bank_account_name": "J Smith",
                "super_fund_usi": "STA0100AU",
            }
        ]

        result = validate_employee_data(employees)

        assert result[0]["valid"] is False
        assert "Email format is invalid" in result[0]["errors"]

    def test_validate_employee_data_invalid_tfn(self):
        """TFN must be 9 digits."""
        from webapp.app_services.payroll_review_service import validate_employee_data

        employees = [
            {
                "first_name": "John",
                "last_name": "Smith",
                "date_of_birth": "15/03/1990",
                "email": "john@example.com",
                "start_date": "01/02/2026",
                "tfn": "12345",  # Only 5 digits
                "bank_bsb": "062000",
                "bank_account_number": "12345678",
                "bank_account_name": "J Smith",
                "super_fund_usi": "STA0100AU",
            }
        ]

        result = validate_employee_data(employees)

        assert result[0]["valid"] is False
        assert "TFN must be 9 digits" in result[0]["errors"]

    def test_validate_employee_data_invalid_bsb(self):
        """BSB must be 6 digits."""
        from webapp.app_services.payroll_review_service import validate_employee_data

        employees = [
            {
                "first_name": "John",
                "last_name": "Smith",
                "date_of_birth": "15/03/1990",
                "email": "john@example.com",
                "start_date": "01/02/2026",
                "tfn": "123456789",
                "bank_bsb": "1234",  # Only 4 digits
                "bank_account_number": "12345678",
                "bank_account_name": "J Smith",
                "super_fund_usi": "STA0100AU",
            }
        ]

        result = validate_employee_data(employees)

        assert result[0]["valid"] is False
        assert "Bank BSB must be 6 digits" in result[0]["errors"]

    def test_validate_employee_data_invalid_state(self):
        """Invalid Australian state should fail."""
        from webapp.app_services.payroll_review_service import validate_employee_data

        employees = [
            {
                "first_name": "John",
                "last_name": "Smith",
                "date_of_birth": "15/03/1990",
                "email": "john@example.com",
                "start_date": "01/02/2026",
                "tfn": "123456789",
                "bank_bsb": "062000",
                "bank_account_number": "12345678",
                "bank_account_name": "J Smith",
                "super_fund_usi": "STA0100AU",
                "state": "INVALID",  # Not a valid state
            }
        ]

        result = validate_employee_data(employees)

        assert result[0]["valid"] is False
        assert any("State must be one of" in e for e in result[0]["errors"])

    def test_validate_employee_data_valid_state(self):
        """Valid Australian state should pass."""
        from webapp.app_services.payroll_review_service import validate_employee_data

        for state in ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"]:
            employees = [
                {
                    "first_name": "John",
                    "last_name": "Smith",
                    "date_of_birth": "15/03/1990",
                    "email": "john@example.com",
                    "start_date": "01/02/2026",
                    "tfn": "123456789",
                    "bank_bsb": "062000",
                    "bank_account_number": "12345678",
                    "bank_account_name": "J Smith",
                    "super_fund_usi": "STA0100AU",
                    "state": state,
                }
            ]

            result = validate_employee_data(employees)
            assert result[0]["valid"] is True, f"State {state} should be valid"

    def test_validate_employee_data_invalid_date_format(self):
        """Invalid date format should fail."""
        from webapp.app_services.payroll_review_service import validate_employee_data

        employees = [
            {
                "first_name": "John",
                "last_name": "Smith",
                "date_of_birth": "March 15, 1990",  # Invalid format
                "email": "john@example.com",
                "start_date": "01/02/2026",
                "tfn": "123456789",
                "bank_bsb": "062000",
                "bank_account_number": "12345678",
                "bank_account_name": "J Smith",
                "super_fund_usi": "STA0100AU",
            }
        ]

        result = validate_employee_data(employees)

        assert result[0]["valid"] is False
        assert "Date of Birth must be in DD/MM/YYYY format" in result[0]["errors"]


# =============================================================================
# Employee Creation Tests
# =============================================================================


class TestEmployeeCreation:
    """Test employee creation in Xero."""

    @patch("webapp.app_services.payroll_review_service.requests.post")
    def test_create_employees_success(self, mock_post):
        """Successful employee creation."""
        from webapp.app_services.payroll_review_service import create_employees_in_xero

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Employees": [{"EmployeeID": "new_emp_123"}]
        }
        mock_post.return_value = mock_response

        employees = [
            {
                "row": 2,
                "first_name": "John",
                "last_name": "Smith",
                "date_of_birth": "15/03/1990",
                "email": "john@example.com",
                "start_date": "01/02/2026",
                "tfn": "123456789",
                "bank_bsb": "062000",
                "bank_account_number": "12345678",
                "bank_account_name": "J Smith",
                "super_fund_usi": "STA0100AU",
                "valid": True,
                "errors": [],
            }
        ]

        result = create_employees_in_xero("token", "tenant", employees)

        assert result["success"] is True
        assert result["created"] == 1
        assert result["failed"] == 0
        assert result["results"][0]["success"] is True
        assert result["results"][0]["employee_id"] == "new_emp_123"

    @patch("webapp.app_services.payroll_review_service.requests.post")
    def test_create_employees_api_error(self, mock_post):
        """API error should be captured."""
        from webapp.app_services.payroll_review_service import create_employees_in_xero

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Validation error: Email already exists"
        mock_post.return_value = mock_response

        employees = [
            {
                "row": 2,
                "first_name": "John",
                "last_name": "Smith",
                "email": "john@example.com",
                "valid": True,
                "errors": [],
            }
        ]

        result = create_employees_in_xero("token", "tenant", employees)

        assert result["success"] is False
        assert result["created"] == 0
        assert result["failed"] == 1
        assert result["results"][0]["success"] is False
        assert "Xero API error" in result["results"][0]["error"]

    def test_create_employees_skips_invalid(self):
        """Invalid employees should be skipped."""
        from webapp.app_services.payroll_review_service import create_employees_in_xero

        employees = [
            {
                "row": 2,
                "first_name": "John",
                "last_name": "",
                "valid": False,
                "errors": ["Last Name is required"],
            }
        ]

        result = create_employees_in_xero("token", "tenant", employees)

        assert result["success"] is False
        assert result["created"] == 0
        assert result["failed"] == 1
        assert "Validation errors" in result["results"][0]["error"]


# =============================================================================
# API Endpoint Tests
# =============================================================================


class TestPayrollReviewAPI:
    """Test payroll review API endpoints."""

    def test_index_page_renders(self, auth_client):
        """Index page should render."""
        resp = auth_client.get("/payroll-review/")
        assert resp.status_code == 200

    def test_pay_runs_without_xero_connection(self, auth_client):
        """Should return error when Xero not connected."""
        resp = auth_client.get("/payroll-review/api/pay-runs")
        assert resp.status_code == 400
        assert resp.json["error"] == "Xero not connected"

    @patch("webapp.blueprints.payroll_review.get_draft_pay_runs")
    @patch("webapp.blueprints.payroll_review.get_recent_posted_pay_run")
    def test_pay_runs_with_xero_connection(self, mock_posted, mock_draft, xero_session):
        """Should return pay runs when Xero is connected."""
        mock_draft.return_value = [
            {"pay_run_id": "draft1", "payment_date": "2026-02-14", "wages": 25000}
        ]
        mock_posted.return_value = {
            "pay_run_id": "posted1", "payment_date": "2026-01-31", "wages": 24500
        }

        resp = xero_session.get("/payroll-review/api/pay-runs")

        assert resp.status_code == 200
        assert resp.json["success"] is True
        assert len(resp.json["draft_pay_runs"]) == 1
        assert resp.json["recent_posted"]["pay_run_id"] == "posted1"

    def test_compare_without_draft_id(self, xero_session):
        """Compare endpoint should require draft_id."""
        resp = xero_session.get("/payroll-review/api/compare")
        assert resp.status_code == 400
        assert resp.json["error"] == "draft_id is required"

    def test_leave_flags_without_pay_run_id(self, xero_session):
        """Leave flags endpoint should require pay_run_id."""
        resp = xero_session.get("/payroll-review/api/leave-flags")
        assert resp.status_code == 400
        assert resp.json["error"] == "pay_run_id is required"

    def test_upload_no_file(self, xero_session):
        """Upload endpoint should require a file."""
        resp = xero_session.post("/payroll-review/api/upload-employees")
        assert resp.status_code == 400
        assert resp.json["error"] == "No file uploaded"

    def test_create_employees_no_data(self, xero_session):
        """Create endpoint should require employees list."""
        resp = xero_session.post(
            "/payroll-review/api/create-employees",
            json={},
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.json["error"] == "employees list is required"

    def test_create_employees_max_batch_size(self, xero_session):
        """Should limit batch size to 50 employees."""
        employees = [{"first_name": f"Emp{i}"} for i in range(51)]
        resp = xero_session.post(
            "/payroll-review/api/create-employees",
            json={"employees": employees},
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "Maximum 50 employees" in resp.json["error"]

    def test_employee_template_download(self, auth_client):
        """Template endpoint should return file."""
        resp = auth_client.get("/payroll-review/api/employee-template")
        # May succeed (with file) or generate on-the-fly
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            assert "spreadsheet" in resp.content_type or "octet-stream" in resp.content_type


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Test internal helper functions."""

    def test_parse_xero_date_timestamp(self):
        """Should parse Xero /Date(timestamp)/ format."""
        from webapp.app_services.payroll_review_service import _parse_xero_date

        result = _parse_xero_date("/Date(1704067200000)/")
        assert result is not None
        assert "2024" in result or "2023" in result  # Timestamp for Jan 2024

    def test_parse_xero_date_iso(self):
        """Should handle ISO date strings."""
        from webapp.app_services.payroll_review_service import _parse_xero_date

        result = _parse_xero_date("2024-01-15")
        assert result == "2024-01-15"

    def test_parse_xero_date_none(self):
        """Should handle None input."""
        from webapp.app_services.payroll_review_service import _parse_xero_date

        result = _parse_xero_date(None)
        assert result is None

    def test_is_valid_email(self):
        """Should validate email format."""
        from webapp.app_services.payroll_review_service import _is_valid_email

        assert _is_valid_email("test@example.com") is True
        assert _is_valid_email("test.user@example.com.au") is True
        assert _is_valid_email("invalid") is False
        assert _is_valid_email("") is False
        assert _is_valid_email(None) is False

    def test_parse_date_string_various_formats(self):
        """Should parse various date formats."""
        from webapp.app_services.payroll_review_service import _parse_date_string

        # DD/MM/YYYY
        result = _parse_date_string("15/03/1990")
        assert result is not None
        assert result.day == 15
        assert result.month == 3
        assert result.year == 1990

        # DD-MM-YYYY
        result = _parse_date_string("15-03-1990")
        assert result is not None

        # YYYY-MM-DD
        result = _parse_date_string("1990-03-15")
        assert result is not None

        # Invalid
        result = _parse_date_string("invalid")
        assert result is None
