"""
Tests for Cash Flow Blueprint

Tests cover:
- GET /cashflow dashboard page
- POST /api/cashflow/analyze endpoint
- GET /api/cashflow/summary endpoint
- POST /api/cashflow/classify endpoint
- Input validation
- Transaction classification logic
- Cash flow statement generation
"""

SAMPLE_TRANSACTIONS = [
    {"date": "2026-01-05", "description": "Sales revenue", "amount": 45000},
    {"date": "2026-01-12", "description": "Wages", "amount": -18000},
    {"date": "2026-01-15", "description": "Rent", "amount": -3500},
    {"date": "2026-01-20", "description": "GST paid", "amount": -2100},
    {"date": "2026-02-01", "description": "Equipment purchase", "amount": -12000},
    {"date": "2026-02-10", "description": "Loan received", "amount": 25000},
    {"date": "2026-02-15", "description": "Loan repayment", "amount": -5000},
    {"date": "2026-02-20", "description": "Owner drawings", "amount": -8000},
]


class TestCashflowDashboard:
    """Tests for GET /cashflow page route."""

    def test_dashboard_returns_200(self, client):
        """Test that the dashboard page renders."""
        response = client.get("/cashflow")
        assert response.status_code == 200

    def test_dashboard_contains_title(self, client):
        """Test that the dashboard contains the page title."""
        response = client.get("/cashflow")
        assert b"Cash Flow Analysis" in response.data


class TestAnalyzeCashflow:
    """Tests for POST /api/cashflow/analyze endpoint."""

    def test_requires_json_body(self, client):
        """Test that JSON body is required."""
        response = client.post("/api/cashflow/analyze")
        assert response.status_code == 400
        data = response.get_json()
        assert "JSON body required" in data["error"]

    def test_requires_transactions(self, client):
        """Test that transactions are required."""
        response = client.post(
            "/api/cashflow/analyze",
            json={"opening_balance": 1000},
            content_type="application/json",
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "transaction" in data["error"].lower()

    def test_rejects_empty_transactions(self, client):
        """Test that empty transactions list is rejected."""
        response = client.post(
            "/api/cashflow/analyze",
            json={"transactions": []},
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_rejects_non_list_transactions(self, client):
        """Test that non-list transactions are rejected."""
        response = client.post(
            "/api/cashflow/analyze",
            json={"transactions": "not a list"},
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_validates_transaction_amount(self, client):
        """Test that transaction amount is validated."""
        response = client.post(
            "/api/cashflow/analyze",
            json={"transactions": [{"description": "Test"}]},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "amount" in response.get_json()["error"].lower()

    def test_validates_transaction_description(self, client):
        """Test that transaction description is required."""
        response = client.post(
            "/api/cashflow/analyze",
            json={"transactions": [{"amount": 100}]},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "description" in response.get_json()["error"].lower()

    def test_validates_invalid_amount_type(self, client):
        """Test that invalid amount type is rejected."""
        response = client.post(
            "/api/cashflow/analyze",
            json={"transactions": [{"description": "Test", "amount": "not_a_number"}]},
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_rejects_too_many_transactions(self, client):
        """Test that more than 10,000 transactions are rejected."""
        txns = [{"description": "Test", "amount": 1}] * 10001
        response = client.post(
            "/api/cashflow/analyze",
            json={"transactions": txns},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "10,000" in response.get_json()["error"]

    def test_successful_analysis(self, client):
        """Test a successful cash flow analysis."""
        response = client.post(
            "/api/cashflow/analyze",
            json={
                "transactions": SAMPLE_TRANSACTIONS,
                "opening_balance": 15000,
                "period_label": "Q1 2026",
            },
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "statement" in data
        assert data["opening_balance"] == 15000
        assert data["period_label"] == "Q1 2026"

    def test_statement_has_three_sections(self, client):
        """Test that statement includes operating, investing, financing."""
        response = client.post(
            "/api/cashflow/analyze",
            json={"transactions": SAMPLE_TRANSACTIONS},
            content_type="application/json",
        )
        data = response.get_json()
        stmt = data["statement"]
        assert "operating" in stmt
        assert "investing" in stmt
        assert "financing" in stmt
        assert "net_cash_change" in stmt

    def test_operating_classification(self, client):
        """Test that operating transactions are classified correctly."""
        response = client.post(
            "/api/cashflow/analyze",
            json={
                "transactions": [
                    {
                        "description": "Sales revenue",
                        "amount": 10000,
                        "date": "2026-01-01",
                    },
                    {"description": "Wages", "amount": -5000, "date": "2026-01-15"},
                ],
            },
            content_type="application/json",
        )
        data = response.get_json()
        stmt = data["statement"]
        assert stmt["operating"]["total_inflows"] == 10000
        assert stmt["operating"]["total_outflows"] == -5000
        assert stmt["operating"]["net"] == 5000

    def test_investing_classification(self, client):
        """Test that investing transactions are classified correctly."""
        response = client.post(
            "/api/cashflow/analyze",
            json={
                "transactions": [
                    {
                        "description": "Equipment purchase",
                        "amount": -12000,
                        "date": "2026-02-01",
                    },
                ],
            },
            content_type="application/json",
        )
        data = response.get_json()
        stmt = data["statement"]
        assert stmt["investing"]["total_outflows"] == -12000
        assert stmt["investing"]["net"] == -12000

    def test_financing_classification(self, client):
        """Test that financing transactions are classified correctly."""
        response = client.post(
            "/api/cashflow/analyze",
            json={
                "transactions": [
                    {
                        "description": "Loan received",
                        "amount": 25000,
                        "date": "2026-02-10",
                    },
                    {
                        "description": "Owner drawings",
                        "amount": -8000,
                        "date": "2026-02-20",
                    },
                ],
            },
            content_type="application/json",
        )
        data = response.get_json()
        stmt = data["statement"]
        assert stmt["financing"]["total_inflows"] == 25000
        assert stmt["financing"]["total_outflows"] == -8000
        assert stmt["financing"]["net"] == 17000

    def test_closing_balance_calculation(self, client):
        """Test that closing balance is calculated correctly."""
        response = client.post(
            "/api/cashflow/analyze",
            json={
                "transactions": [
                    {
                        "description": "Sales revenue",
                        "amount": 10000,
                        "date": "2026-01-01",
                    },
                    {"description": "Wages", "amount": -3000, "date": "2026-01-15"},
                ],
                "opening_balance": 5000,
            },
            content_type="application/json",
        )
        data = response.get_json()
        assert data["opening_balance"] == 5000
        assert data["closing_balance"] == 12000  # 5000 + 10000 - 3000

    def test_default_opening_balance(self, client):
        """Test that opening balance defaults to 0."""
        response = client.post(
            "/api/cashflow/analyze",
            json={
                "transactions": [
                    {
                        "description": "Sales revenue",
                        "amount": 1000,
                        "date": "2026-01-01",
                    },
                ],
            },
            content_type="application/json",
        )
        data = response.get_json()
        assert data["opening_balance"] == 0

    def test_transaction_count(self, client):
        """Test that transaction count is reported."""
        response = client.post(
            "/api/cashflow/analyze",
            json={"transactions": SAMPLE_TRANSACTIONS},
            content_type="application/json",
        )
        data = response.get_json()
        assert data["statement"]["transaction_count"] == len(SAMPLE_TRANSACTIONS)


class TestCashflowSummary:
    """Tests for GET /api/cashflow/summary endpoint."""

    def test_returns_summary(self, client):
        """Test that summary endpoint returns data."""
        response = client.get("/api/cashflow/summary")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "summary" in data

    def test_summary_structure(self, client):
        """Test that summary has the expected structure."""
        response = client.get("/api/cashflow/summary")
        data = response.get_json()
        summary = data["summary"]
        assert "period" in summary
        assert "operating" in summary
        assert "investing" in summary
        assert "financing" in summary
        assert "net_cash_change" in summary

    def test_custom_period(self, client):
        """Test that custom period label is returned."""
        response = client.get("/api/cashflow/summary?period=Q4+2025")
        data = response.get_json()
        assert data["summary"]["period"] == "Q4 2025"


class TestClassifyTransaction:
    """Tests for POST /api/cashflow/classify endpoint."""

    def test_requires_json_body(self, client):
        """Test that JSON body is required."""
        response = client.post("/api/cashflow/classify")
        assert response.status_code == 400

    def test_requires_transactions(self, client):
        """Test that transactions are required."""
        response = client.post(
            "/api/cashflow/classify",
            json={},
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_classifies_operating(self, client):
        """Test classification of operating transactions."""
        response = client.post(
            "/api/cashflow/classify",
            json={"transactions": [{"description": "Wages paid"}]},
            content_type="application/json",
        )
        data = response.get_json()
        assert data["success"] is True
        assert data["classifications"][0]["category"] == "operating"

    def test_classifies_investing(self, client):
        """Test classification of investing transactions."""
        response = client.post(
            "/api/cashflow/classify",
            json={"transactions": [{"description": "Equipment purchase"}]},
            content_type="application/json",
        )
        data = response.get_json()
        assert data["classifications"][0]["category"] == "investing"

    def test_classifies_financing(self, client):
        """Test classification of financing transactions."""
        response = client.post(
            "/api/cashflow/classify",
            json={"transactions": [{"description": "Loan received from bank"}]},
            content_type="application/json",
        )
        data = response.get_json()
        assert data["classifications"][0]["category"] == "financing"

    def test_batch_classification(self, client):
        """Test classification of multiple transactions."""
        response = client.post(
            "/api/cashflow/classify",
            json={
                "transactions": [
                    {"description": "Sales revenue"},
                    {"description": "Equipment purchase"},
                    {"description": "Loan repayment"},
                ],
            },
            content_type="application/json",
        )
        data = response.get_json()
        assert len(data["classifications"]) == 3
        assert data["classifications"][0]["category"] == "operating"
        assert data["classifications"][1]["category"] == "investing"
        assert data["classifications"][2]["category"] == "financing"

    def test_rejects_too_many_transactions(self, client):
        """Test that more than 1,000 transactions are rejected."""
        txns = [{"description": "Test"}] * 1001
        response = client.post(
            "/api/cashflow/classify",
            json={"transactions": txns},
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_uses_account_for_classification(self, client):
        """Test that account field is used in classification."""
        response = client.post(
            "/api/cashflow/classify",
            json={
                "transactions": [
                    {"description": "Payment", "account": "Equipment purchase"},
                ],
            },
            content_type="application/json",
        )
        data = response.get_json()
        assert data["classifications"][0]["category"] == "investing"


class TestClassifyTransactionUnit:
    """Unit tests for classify_transaction function."""

    def test_operating_keywords(self):
        """Test operating activity keywords."""
        from webapp.blueprints.cashflow import classify_transaction

        cat, _ = classify_transaction("Monthly rent payment")
        assert cat == "operating"

        cat, _ = classify_transaction("Insurance premium")
        assert cat == "operating"

        cat, _ = classify_transaction("Superannuation contribution")
        assert cat == "operating"

    def test_investing_keywords(self):
        """Test investing activity keywords."""
        from webapp.blueprints.cashflow import classify_transaction

        cat, _ = classify_transaction("Vehicle purchase")
        assert cat == "investing"

        cat, _ = classify_transaction("Computer equipment")
        assert cat == "investing"

    def test_financing_keywords(self):
        """Test financing activity keywords."""
        from webapp.blueprints.cashflow import classify_transaction

        cat, _ = classify_transaction("Owner drawings")
        assert cat == "financing"

        cat, _ = classify_transaction("Capital contribution")
        assert cat == "financing"

    def test_unknown_defaults_to_operating(self):
        """Test that unknown transactions default to operating."""
        from webapp.blueprints.cashflow import classify_transaction

        cat, subcat = classify_transaction("Unknown transaction xyz")
        assert cat == "operating"
        assert subcat == "other"


class TestBuildCashflowStatement:
    """Unit tests for build_cashflow_statement function."""

    def test_empty_transactions(self):
        """Test with no transactions."""
        from webapp.blueprints.cashflow import build_cashflow_statement

        result = build_cashflow_statement([])
        assert result["net_cash_change"] == 0
        assert result["transaction_count"] == 0

    def test_mixed_transactions(self):
        """Test with a mix of operating, investing, financing."""
        from webapp.blueprints.cashflow import build_cashflow_statement

        result = build_cashflow_statement(SAMPLE_TRANSACTIONS)
        assert result["transaction_count"] == len(SAMPLE_TRANSACTIONS)
        assert "operating" in result
        assert "investing" in result
        assert "financing" in result

        # Net change should equal sum of all amounts
        total = sum(t["amount"] for t in SAMPLE_TRANSACTIONS)
        assert result["net_cash_change"] == total

    def test_inflows_and_outflows_separated(self):
        """Test that inflows and outflows are properly separated."""
        from webapp.blueprints.cashflow import build_cashflow_statement

        txns = [
            {"description": "Sales revenue", "amount": 10000, "date": "2026-01-01"},
            {"description": "Wages", "amount": -5000, "date": "2026-01-15"},
        ]
        result = build_cashflow_statement(txns)
        assert len(result["operating"]["inflows"]) == 1
        assert len(result["operating"]["outflows"]) == 1
