"""Tests for super guarantee reconciliation service and blueprint."""

from datetime import date
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
def db(app):
    from webapp.models import db as _db

    return _db


def _register(client, email="test@test.com"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": "password123", "name": "Test User"},
    )


# =============================================================================
# Service Tests - Quarter & Deadline Calculation
# =============================================================================


class TestGetSgQuarterAndDeadline:
    """Tests for SG quarter and deadline calculation."""

    def test_q1_jul_sep(self, app):
        from webapp.app_services.super_reconciliation_service import (
            _get_sg_quarter_and_deadline,
        )

        result = _get_sg_quarter_and_deadline(date(2024, 7, 1), date(2024, 9, 30))
        assert result["quarter"] == 1
        assert "Q1 Jul-Sep" in result["label"]
        assert result["deadline"] == "2024-10-28"
        assert result["sg_rate"] == 0.115

    def test_q2_oct_dec(self, app):
        from webapp.app_services.super_reconciliation_service import (
            _get_sg_quarter_and_deadline,
        )

        result = _get_sg_quarter_and_deadline(date(2024, 10, 1), date(2024, 12, 31))
        assert result["quarter"] == 2
        assert "Q2 Oct-Dec" in result["label"]
        # Q2 deadline is Feb next year
        assert result["deadline"] == "2025-02-28"

    def test_q3_jan_mar(self, app):
        from webapp.app_services.super_reconciliation_service import (
            _get_sg_quarter_and_deadline,
        )

        result = _get_sg_quarter_and_deadline(date(2025, 1, 1), date(2025, 3, 31))
        assert result["quarter"] == 3
        assert result["deadline"] == "2025-04-28"

    def test_q4_apr_jun(self, app):
        from webapp.app_services.super_reconciliation_service import (
            _get_sg_quarter_and_deadline,
        )

        result = _get_sg_quarter_and_deadline(date(2025, 4, 1), date(2025, 6, 30))
        assert result["quarter"] == 4
        assert result["deadline"] == "2025-07-28"

    def test_sg_rate_2025(self, app):
        from webapp.app_services.super_reconciliation_service import (
            _get_sg_quarter_and_deadline,
        )

        result = _get_sg_quarter_and_deadline(date(2025, 7, 1), date(2025, 9, 30))
        assert result["sg_rate"] == 0.12

    def test_sg_rate_2024(self, app):
        from webapp.app_services.super_reconciliation_service import (
            _get_sg_quarter_and_deadline,
        )

        result = _get_sg_quarter_and_deadline(date(2024, 7, 1), date(2024, 9, 30))
        assert result["sg_rate"] == 0.115


# =============================================================================
# Service Tests - Evaluate Super Result
# =============================================================================


class TestEvaluateSuperResult:
    """Tests for super result evaluation."""

    def test_fully_paid_on_time(self, app):
        from webapp.app_services.super_reconciliation_service import (
            _evaluate_super_result,
        )

        result = _evaluate_super_result(
            total_liability=10000,
            total_paid=10000,
            has_late_payments=False,
            deadline="2099-12-31",
        )
        assert result["status"] == "pass"
        assert result["status_label"] == "FULLY PAID"
        assert result["variance"] == 0

    def test_overpaid(self, app):
        from webapp.app_services.super_reconciliation_service import (
            _evaluate_super_result,
        )

        result = _evaluate_super_result(
            total_liability=10000,
            total_paid=12000,
            has_late_payments=False,
            deadline="2099-12-31",
        )
        assert result["status"] == "pass"
        assert result["variance"] == -2000

    def test_paid_but_late(self, app):
        from webapp.app_services.super_reconciliation_service import (
            _evaluate_super_result,
        )

        result = _evaluate_super_result(
            total_liability=10000,
            total_paid=10000,
            has_late_payments=True,
            deadline="2099-12-31",
        )
        assert result["status"] == "warning"
        assert "LATE" in result["status_label"]

    def test_underpaid_before_deadline(self, app):
        from webapp.app_services.super_reconciliation_service import (
            _evaluate_super_result,
        )

        result = _evaluate_super_result(
            total_liability=10000,
            total_paid=5000,
            has_late_payments=False,
            deadline="2099-12-31",
        )
        assert result["status"] == "warning"
        assert result["variance"] == 5000

    def test_underpaid_past_deadline(self, app):
        from webapp.app_services.super_reconciliation_service import (
            _evaluate_super_result,
        )

        result = _evaluate_super_result(
            total_liability=10000,
            total_paid=2000,
            has_late_payments=False,
            deadline="2020-01-01",
        )
        assert result["status"] == "fail"
        assert result["is_past_deadline"] is True
        assert result["variance"] == 8000
        assert "SGC" in result["message"]


# =============================================================================
# Service Tests - Employee Super Breakdown
# =============================================================================


class TestGetEmployeeSuperBreakdown:
    """Tests for employee super breakdown with mocked Xero API."""

    @patch("webapp.app_services.super_reconciliation_service._xero_payroll_request")
    def test_single_employee(self, mock_payroll, app):
        from webapp.app_services.super_reconciliation_service import (
            get_employee_super_breakdown,
        )

        # First call: list pay runs
        mock_payroll.side_effect = [
            {
                "PayRuns": [
                    {
                        "PayRunID": "pr-1",
                        "PayRunPeriodEndDate": "2024-08-31",
                        "PayRunStatus": "POSTED",
                    }
                ]
            },
            # Second call: pay run detail
            {
                "PayRuns": [
                    {
                        "Payslips": [
                            {
                                "EmployeeID": "emp-1",
                                "FirstName": "Jane",
                                "LastName": "Smith",
                                "Wages": 5000,
                                "Super": 575,
                            }
                        ]
                    }
                ]
            },
        ]

        result = get_employee_super_breakdown(
            "token", "tenant", date(2024, 7, 1), date(2024, 9, 30), 0.115
        )

        assert result["success"] is True
        assert result["has_payroll"] is True
        assert len(result["employees"]) == 1
        assert result["employees"][0]["name"] == "Jane Smith"
        assert result["employees"][0]["gross_earnings"] == 5000
        assert result["employees"][0]["expected_super"] == 575
        assert result["total_liability"] == 575

    @patch("webapp.app_services.super_reconciliation_service._xero_payroll_request")
    def test_multiple_employees(self, mock_payroll, app):
        from webapp.app_services.super_reconciliation_service import (
            get_employee_super_breakdown,
        )

        mock_payroll.side_effect = [
            {
                "PayRuns": [
                    {
                        "PayRunID": "pr-1",
                        "PayRunPeriodEndDate": "2024-08-31",
                        "PayRunStatus": "POSTED",
                    }
                ]
            },
            {
                "PayRuns": [
                    {
                        "Payslips": [
                            {
                                "EmployeeID": "emp-1",
                                "FirstName": "Alice",
                                "LastName": "Brown",
                                "Wages": 6000,
                                "Super": 690,
                            },
                            {
                                "EmployeeID": "emp-2",
                                "FirstName": "Bob",
                                "LastName": "Jones",
                                "Wages": 4000,
                                "Super": 460,
                            },
                        ]
                    }
                ]
            },
        ]

        result = get_employee_super_breakdown(
            "token", "tenant", date(2024, 7, 1), date(2024, 9, 30), 0.115
        )

        assert result["success"] is True
        assert len(result["employees"]) == 2
        assert result["total_liability"] == 1150  # (6000+4000) * 0.115

    @patch("webapp.app_services.super_reconciliation_service._xero_payroll_request")
    def test_no_payroll_access(self, mock_payroll, app):
        from webapp.app_services.super_reconciliation_service import (
            get_employee_super_breakdown,
        )

        mock_payroll.return_value = {"error": "No payroll access", "status_code": 403}

        result = get_employee_super_breakdown(
            "token", "tenant", date(2024, 7, 1), date(2024, 9, 30), 0.115
        )

        assert result["success"] is True
        assert result["has_payroll"] is False
        assert len(result["employees"]) == 0

    @patch("webapp.app_services.super_reconciliation_service._xero_payroll_request")
    def test_no_pay_runs(self, mock_payroll, app):
        from webapp.app_services.super_reconciliation_service import (
            get_employee_super_breakdown,
        )

        mock_payroll.return_value = {"PayRuns": []}

        result = get_employee_super_breakdown(
            "token", "tenant", date(2024, 7, 1), date(2024, 9, 30), 0.115
        )

        assert result["success"] is True
        assert result["has_payroll"] is True
        assert len(result["employees"]) == 0
        assert result["total_liability"] == 0


# =============================================================================
# Service Tests - Super Payments
# =============================================================================


class TestGetSuperPayments:
    """Tests for fetching super payments."""

    @patch("webapp.app_services.super_reconciliation_service._xero_api_request")
    def test_on_time_payments(self, mock_api, app):
        from webapp.app_services.super_reconciliation_service import (
            get_super_payments,
        )

        mock_api.side_effect = [
            # Accounts response
            {
                "Accounts": [
                    {"AccountID": "acct-1", "Name": "Superannuation Payable"},
                    {"AccountID": "acct-2", "Name": "Bank Account"},
                ]
            },
            # Bank transactions response
            {
                "BankTransactions": [
                    {
                        "Date": "2024-10-15",
                        "Reference": "Super payment Oct",
                        "Total": 5000,
                        "Contact": {"Name": "Super Fund"},
                        "LineItems": [{"AccountID": "acct-1"}],
                    }
                ]
            },
        ]

        result = get_super_payments(
            "token", "tenant", date(2024, 7, 1), date(2024, 9, 30), "2024-10-28"
        )

        assert result["success"] is True
        assert len(result["payments"]) == 1
        assert result["total_paid"] == 5000
        assert result["has_late_payments"] is False
        assert result["payments"][0]["is_late"] is False

    @patch("webapp.app_services.super_reconciliation_service._xero_api_request")
    def test_late_payment_flagging(self, mock_api, app):
        from webapp.app_services.super_reconciliation_service import (
            get_super_payments,
        )

        mock_api.side_effect = [
            {
                "Accounts": [
                    {"AccountID": "acct-1", "Name": "Super Guarantee"},
                ]
            },
            {
                "BankTransactions": [
                    {
                        "Date": "2024-11-15",  # After Oct 28 deadline
                        "Reference": "Late super",
                        "Total": 3000,
                        "Contact": {"Name": "Super Fund"},
                        "LineItems": [{"AccountID": "acct-1"}],
                    }
                ]
            },
        ]

        result = get_super_payments(
            "token", "tenant", date(2024, 7, 1), date(2024, 9, 30), "2024-10-28"
        )

        assert result["success"] is True
        assert result["has_late_payments"] is True
        assert result["payments"][0]["is_late"] is True

    @patch("webapp.app_services.super_reconciliation_service._xero_api_request")
    def test_no_super_accounts(self, mock_api, app):
        from webapp.app_services.super_reconciliation_service import (
            get_super_payments,
        )

        mock_api.return_value = {
            "Accounts": [
                {"AccountID": "acct-1", "Name": "Bank Account"},
                {"AccountID": "acct-2", "Name": "Sales Revenue"},
            ]
        }

        result = get_super_payments(
            "token", "tenant", date(2024, 7, 1), date(2024, 9, 30), "2024-10-28"
        )

        assert result["success"] is True
        assert len(result["payments"]) == 0
        assert result["total_paid"] == 0

    @patch("webapp.app_services.super_reconciliation_service._xero_api_request")
    def test_api_error(self, mock_api, app):
        from webapp.app_services.super_reconciliation_service import (
            get_super_payments,
        )

        mock_api.return_value = {"error": "Unauthorized", "status_code": 401}

        result = get_super_payments(
            "token", "tenant", date(2024, 7, 1), date(2024, 9, 30), "2024-10-28"
        )

        assert result["success"] is False


# =============================================================================
# Service Tests - Generate Full Reconciliation
# =============================================================================


class TestGenerateSuperReconciliation:
    """Tests for the main reconciliation entry point."""

    @patch("webapp.app_services.super_reconciliation_service.get_super_payments")
    @patch("webapp.app_services.super_reconciliation_service.get_employee_super_breakdown")
    def test_full_payment_pass(self, mock_emp, mock_pay, app):
        from webapp.app_services.super_reconciliation_service import (
            generate_super_reconciliation,
        )

        mock_emp.return_value = {
            "success": True,
            "has_payroll": True,
            "employees": [
                {
                    "name": "Jane Smith",
                    "gross_earnings": 20000,
                    "sg_rate": 0.115,
                    "expected_super": 2300,
                    "payslip_super": 2300,
                }
            ],
            "total_liability": 2300,
            "total_payslip_super": 2300,
            "error": None,
        }

        mock_pay.return_value = {
            "success": True,
            "payments": [
                {
                    "date": "2024-10-15",
                    "date_display": "15 Oct 2024",
                    "description": "Super payment",
                    "account_name": "Superannuation",
                    "amount": 2300,
                    "is_late": False,
                }
            ],
            "total_paid": 2300,
            "has_late_payments": False,
            "error": None,
        }

        result = generate_super_reconciliation(
            "token", "tenant", date(2024, 7, 1), date(2024, 9, 30)
        )

        assert result["success"] is True
        assert result["summary"]["status"] == "pass"
        assert result["summary"]["variance"] == 0
        assert len(result["employees"]) == 1

    @patch("webapp.app_services.super_reconciliation_service.get_super_payments")
    @patch("webapp.app_services.super_reconciliation_service.get_employee_super_breakdown")
    def test_underpaid_fail(self, mock_emp, mock_pay, app):
        from webapp.app_services.super_reconciliation_service import (
            generate_super_reconciliation,
        )

        mock_emp.return_value = {
            "success": True,
            "has_payroll": True,
            "employees": [
                {
                    "name": "John Doe",
                    "gross_earnings": 30000,
                    "sg_rate": 0.115,
                    "expected_super": 3450,
                    "payslip_super": 3450,
                }
            ],
            "total_liability": 3450,
            "total_payslip_super": 3450,
            "error": None,
        }

        mock_pay.return_value = {
            "success": True,
            "payments": [],
            "total_paid": 0,
            "has_late_payments": False,
            "error": None,
        }

        result = generate_super_reconciliation(
            "token", "tenant", date(2024, 7, 1), date(2024, 9, 30)
        )

        assert result["success"] is True
        assert result["summary"]["variance"] == 3450
        # Status depends on whether deadline has passed
        assert result["summary"]["status"] in ("warning", "fail")

    @patch("webapp.app_services.super_reconciliation_service.get_super_payments")
    @patch("webapp.app_services.super_reconciliation_service.get_employee_super_breakdown")
    def test_payroll_error(self, mock_emp, mock_pay, app):
        from webapp.app_services.super_reconciliation_service import (
            generate_super_reconciliation,
        )

        mock_emp.return_value = {
            "success": False,
            "has_payroll": False,
            "employees": [],
            "error": "API error",
        }

        result = generate_super_reconciliation(
            "token", "tenant", date(2024, 7, 1), date(2024, 9, 30)
        )

        assert result["success"] is False
        assert result["error"] is not None


# =============================================================================
# Service Tests - Email Reminder
# =============================================================================


class TestSendSuperReminderEmail:
    """Tests for sending reminder emails."""

    @patch("webapp.app_services.super_reconciliation_service.requests.post")
    @patch.dict("os.environ", {"RESEND_API_KEY": "test-key"})
    def test_successful_send(self, mock_post, app):
        from webapp.app_services.super_reconciliation_service import (
            send_super_reminder_email,
        )

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"id": "email-123"}
        mock_post.return_value = mock_response

        result = send_super_reminder_email(
            to_email="client@example.com",
            quarter_label="Q1 Jul-Sep 2024",
            deadline="28 Oct 2024",
            total_liability=10000,
            total_paid=2000,
            variance=8000,
            status="fail",
            tenant_name="Test Pty Ltd",
        )

        assert result["success"] is True
        assert result["email_sent"] is True
        mock_post.assert_called_once()

        # Verify email content
        call_kwargs = mock_post.call_args
        email_json = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert email_json["to"] == ["client@example.com"]
        assert "Super Guarantee Reminder" in email_json["subject"]
        assert "Test Pty Ltd" in email_json["subject"]

    @patch("webapp.app_services.super_reconciliation_service.requests.post")
    @patch.dict("os.environ", {"RESEND_API_KEY": "test-key"})
    def test_email_failure_graceful(self, mock_post, app):
        import requests as req

        from webapp.app_services.super_reconciliation_service import (
            send_super_reminder_email,
        )

        mock_post.side_effect = req.exceptions.ConnectionError("Connection refused")

        result = send_super_reminder_email(
            to_email="client@example.com",
            quarter_label="Q1 Jul-Sep 2024",
            deadline="28 Oct 2024",
            total_liability=10000,
            total_paid=2000,
            variance=8000,
            status="fail",
            tenant_name="Test Pty Ltd",
        )

        assert result["success"] is False
        assert result["email_sent"] is False
        assert result["error"] is not None

    @patch.dict("os.environ", {}, clear=True)
    def test_no_api_key(self, app):
        import os

        from webapp.app_services.super_reconciliation_service import (
            send_super_reminder_email,
        )

        # Remove env var entirely
        os.environ.pop("RESEND_API_KEY", None)

        result = send_super_reminder_email(
            to_email="client@example.com",
            quarter_label="Q1 Jul-Sep 2024",
            deadline="28 Oct 2024",
            total_liability=10000,
            total_paid=2000,
            variance=8000,
            status="fail",
            tenant_name="Test Pty Ltd",
        )

        assert result["success"] is False
        assert result["email_sent"] is False
        assert "not configured" in result["error"]


# =============================================================================
# Blueprint Tests
# =============================================================================


class TestSuperReconciliationBlueprint:
    """Tests for super reconciliation API endpoints."""

    def test_page_renders(self, client):
        """Test that the page renders for authenticated users."""
        _register(client)
        res = client.get("/super-reconciliation/")
        assert res.status_code == 200
        assert b"Super Guarantee Reconciliation" in res.data

    def test_generate_requires_dates(self, client):
        """Test that generate endpoint requires date params."""
        _register(client)
        res = client.get("/super-reconciliation/api/generate")
        assert res.status_code == 400

    def test_generate_requires_credentials(self, client):
        """Test that generate endpoint requires Xero credentials."""
        _register(client)
        res = client.get(
            "/super-reconciliation/api/generate?from_date=2024-07-01&to_date=2024-09-30"
        )
        assert res.status_code == 400
        data = res.get_json()
        assert "access_token" in data["error"]

    def test_generate_validates_date_range(self, client):
        """Test date range validation."""
        _register(client)
        res = client.get(
            "/super-reconciliation/api/generate"
            "?from_date=2024-09-30&to_date=2024-07-01"
            "&access_token=test&tenant_id=test"
        )
        assert res.status_code == 400
        assert "before" in res.get_json()["error"]

    def test_send_reminder_requires_email(self, client):
        """Test that send reminder requires valid email."""
        _register(client)
        res = client.post(
            "/super-reconciliation/api/send-reminder",
            json={
                "email": "not-valid",
                "quarter_label": "Q1",
                "deadline": "28 Oct 2024",
                "tenant_name": "Test",
            },
        )
        assert res.status_code == 400

    def test_send_reminder_requires_fields(self, client):
        """Test that send reminder requires all fields."""
        _register(client)
        res = client.post(
            "/super-reconciliation/api/send-reminder",
            json={"email": "test@example.com"},
        )
        assert res.status_code == 400

    def test_get_client_email(self, client):
        """Test getting client email."""
        _register(client)
        res = client.get("/super-reconciliation/api/client-email")
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True

    def test_save_client_email(self, client):
        """Test saving and retrieving client email."""
        _register(client)

        # Save email
        res = client.post(
            "/super-reconciliation/api/client-email",
            json={"email": "client@example.com"},
        )
        assert res.status_code == 200
        assert res.get_json()["success"] is True

        # Retrieve email
        res = client.get("/super-reconciliation/api/client-email")
        assert res.status_code == 200
        assert res.get_json()["email"] == "client@example.com"

    def test_save_client_email_validation(self, client):
        """Test email validation on save."""
        _register(client)
        res = client.post(
            "/super-reconciliation/api/client-email",
            json={"email": "bad-email"},
        )
        assert res.status_code == 400
