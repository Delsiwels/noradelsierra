"""Regression tests for Ask Fin journal review endpoints and parser."""

from __future__ import annotations

import io

import pytest

from webapp.config import TestingConfig
from webapp.services.journal_parser import format_entries_for_review, parse_journal_csv

VALID_CSV = """\
Date,Account,Description,Debit,Credit,GST Code
2026-01-15,Bank Fees,Monthly fee,55.00,0.00,BAS Excluded
2026-01-15,Cash at Bank,Monthly fee,0.00,55.00,BAS Excluded
"""


@pytest.fixture
def app():
    from webapp.app import create_app
    from webapp.models import db

    app = create_app(TestingConfig)
    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _register(client):
    return client.post(
        "/api/auth/register",
        json={
            "email": "ask-fin@test.com",
            "password": "password123",
            "name": "Ask Fin User",
        },
    )


def test_parse_journal_csv_accepts_alias_columns():
    csv_text = "Date,Account,Dr,Cr\n2026-01-01,Bank,100,0\n"
    parsed = parse_journal_csv(csv_text)

    assert parsed.error is None
    assert parsed.row_count == 1
    assert "debit" in parsed.columns
    assert "credit" in parsed.columns


def test_parse_journal_csv_missing_required_column():
    parsed = parse_journal_csv("Account,Debit,Credit\nBank,100,100\n")

    assert parsed.error is not None
    assert "Missing required columns" in parsed.error
    assert "Date" in parsed.error


def test_format_entries_marks_unbalanced_batches():
    parsed = parse_journal_csv("Date,Account,Debit,Credit\n2026-01-01,Bank,100,0\n")
    summary = format_entries_for_review(parsed)

    assert "WARNING" in summary
    assert "Total Debits" in summary


def test_tax_agent_page_requires_login(client):
    response = client.get("/ask-fin/tax-agent")
    assert response.status_code == 401


def test_tax_agent_page_renders_for_authenticated_user(client):
    _register(client)
    response = client.get("/ask-fin/tax-agent")

    assert response.status_code == 200
    assert b"Ask Fin" in response.data
    assert b"Tax Agent" in response.data


def test_review_journal_rejects_missing_upload(client):
    _register(client)
    response = client.post("/api/ask-fin/review-journal")

    assert response.status_code == 400
    assert "No file" in response.get_json()["error"]


def test_review_journal_rejects_non_csv_upload(client):
    _register(client)
    response = client.post(
        "/api/ask-fin/review-journal",
        data={"file": (io.BytesIO(b"hello"), "bad.xlsx")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert "CSV" in response.get_json()["error"]


def test_review_journal_returns_parsed_summary(client):
    _register(client)
    response = client.post(
        "/api/ask-fin/review-journal",
        data={"file": (io.BytesIO(VALID_CSV.encode("utf-8")), "journals.csv")},
        content_type="multipart/form-data",
    )

    assert response.status_code in (200, 503)
    payload = response.get_json()
    assert "journal_summary" in payload
    assert "journal entries" in payload["journal_summary"]
