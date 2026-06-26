"""Tests for the cash flow forecast service (extracted from the blueprint).

The blueprint never had coverage for the Xero fetch/compute path; these tests
mock Xero and exercise the service directly.
"""

from unittest.mock import MagicMock, patch

from webapp.app_services import forecast_service


def _mock_response(payload):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    return resp


ACCOUNTS_PAYLOAD = {
    "Accounts": [
        {"Name": "Business", "BankAccountBalance": 10000, "AccountID": "a1"},
        {"Name": "Savings", "BankAccountBalance": 5000, "AccountID": "a2"},
    ]
}

TXN_PAYLOAD = {
    "BankTransactions": [
        {"Total": 5000, "Type": "RECEIVE", "Date": "/Date(1704067200000)/"},
        {"Total": 3000, "Type": "SPEND", "Date": "/Date(1704067200000)/"},
    ]
}


def test_fetch_bank_accounts_shapes_and_totals():
    with patch.object(
        forecast_service.requests, "get", return_value=_mock_response(ACCOUNTS_PAYLOAD)
    ):
        accounts, total_cash = forecast_service.fetch_bank_accounts("tok", "tenant")

    assert total_cash == 15000.0
    assert accounts[0] == {"name": "Business", "balance": 10000.0, "id": "a1"}
    assert accounts[1]["name"] == "Savings"


def test_generate_cash_flow_forecast_structure():
    with patch.object(
        forecast_service.requests,
        "get",
        side_effect=[
            _mock_response(ACCOUNTS_PAYLOAD),
            _mock_response(TXN_PAYLOAD),
        ],
    ):
        result = forecast_service.generate_cash_flow_forecast("tok", "tenant", "self")

    # Structural contract the blueprint serialises to JSON
    assert set(result) == {
        "accounts",
        "total_cash",
        "months",
        "risk_indicators",
        "deadlines",
        "summary",
    }
    assert result["total_cash"] == 15000.0
    assert len(result["months"]) == 12
    assert result["summary"]["avg_monthly_inflow"] == 5000.0
    assert result["summary"]["avg_monthly_outflow"] == 3000.0
    assert result["summary"]["current_cash"] == 15000.0
    # Each projected month carries the expected keys
    first = result["months"][0]
    assert {"month", "month_key", "inflows", "outflows", "net", "balance"} <= set(first)


def test_generate_handles_no_transactions():
    with patch.object(
        forecast_service.requests,
        "get",
        side_effect=[
            _mock_response(ACCOUNTS_PAYLOAD),
            _mock_response({"BankTransactions": []}),
        ],
    ):
        result = forecast_service.generate_cash_flow_forecast("tok", "tenant", "agent")

    assert result["summary"]["avg_monthly_inflow"] == 0
    assert result["summary"]["avg_monthly_outflow"] == 0
    assert len(result["months"]) == 12
