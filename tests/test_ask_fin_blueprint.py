"""Regression tests for Ask Fin journal review endpoints and parser."""

from __future__ import annotations

import io
import uuid

import pytest
from flask_bcrypt import generate_password_hash

from webapp.ai.models import ChatResponse
from webapp.config import TestingConfig
from webapp.models import Team, User, db
from webapp.services.journal_parser import (
    MAX_FILE_SIZE,
    MAX_ROWS,
    format_entries_for_review,
    parse_journal_csv,
)

VALID_CSV = """\
Date,Account,Description,Debit,Credit,GST Code
2026-01-15,Bank Fees,Monthly fee,55.00,0.00,BAS Excluded
2026-01-15,Cash at Bank,Monthly fee,0.00,55.00,BAS Excluded
"""


@pytest.fixture
def app():
    from webapp.app import create_app

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


def test_parse_journal_csv_truncates_excess_rows():
    header = "Date,Account,Debit,Credit\n"
    rows = "".join(
        f"2026-01-01,Account {index},100,100\n" for index in range(MAX_ROWS + 100)
    )
    parsed = parse_journal_csv(header + rows)

    assert parsed.error is None
    assert parsed.row_count == MAX_ROWS
    assert parsed.warnings


def test_parse_journal_csv_rejects_oversized_bytes():
    payload = b"x" * (MAX_FILE_SIZE + 1)
    parsed = parse_journal_csv(payload)

    assert parsed.error is not None
    assert "too large" in parsed.error.lower()


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


def test_tax_agent_page_escapes_display_name(client, app):
    user_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())
    raw_name = "<script>alert('xss')</script>"

    with app.app_context():
        team = Team(id=team_id, name="Security Team", owner_id=user_id)
        user = User(
            id=user_id,
            email="xss@test.com",
            password_hash=generate_password_hash("password123").decode("utf-8"),
            name=raw_name,
            role="owner",
            team_id=team_id,
        )
        db.session.add(team)
        db.session.add(user)
        db.session.commit()

    login_response = client.post(
        "/api/auth/login",
        json={"email": "xss@test.com", "password": "password123"},
    )
    assert login_response.status_code == 200

    response = client.get("/ask-fin/tax-agent")
    assert response.status_code == 200
    assert b"&lt;script&gt;alert" in response.data
    assert b"<script>alert" not in response.data


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


def test_review_journal_returns_ai_review_when_service_available(client, monkeypatch):
    _register(client)

    class _StubService:
        def send_message(self, **_kwargs):
            return ChatResponse(
                content="Detected one GST coding issue on row 2.",
                skills_used=["tax_agent"],
                model="stub-model",
                usage={"input": 10, "output": 15},
            )

    monkeypatch.setattr(
        "webapp.blueprints.ask_fin.get_chat_service", lambda: _StubService()
    )

    response = client.post(
        "/api/ask-fin/review-journal",
        data={"file": (io.BytesIO(VALID_CSV.encode("utf-8")), "journals.csv")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["review"] == "Detected one GST coding issue on row 2."
    assert payload["model"] == "stub-model"
    assert payload["skills_used"] == ["tax_agent"]


def test_review_journal_returns_503_when_ai_review_fails(client, monkeypatch):
    _register(client)

    class _FailingService:
        def send_message(self, **_kwargs):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        "webapp.blueprints.ask_fin.get_chat_service",
        lambda: _FailingService(),
    )

    response = client.post(
        "/api/ask-fin/review-journal",
        data={"file": (io.BytesIO(VALID_CSV.encode("utf-8")), "journals.csv")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 503
    payload = response.get_json()
    assert "journal_summary" in payload
    assert payload["error"] == "AI review generation failed."


def test_review_journal_rejects_oversized_file(client):
    _register(client)
    too_large = b"x" * (MAX_FILE_SIZE + 1)
    response = client.post(
        "/api/ask-fin/review-journal",
        data={"file": (io.BytesIO(too_large), "too-large.csv")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert "too large" in response.get_json()["error"].lower()
