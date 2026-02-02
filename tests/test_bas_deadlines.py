"""Tests for BAS deadline service."""

from datetime import date

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


class TestQuarterlyDeadlines:
    """Test quarterly BAS deadline calculations."""

    def test_q1_deadline(self, app):
        """Q1 (Jul-Sep) due 28 Oct."""
        from webapp.services.bas_deadlines import get_upcoming_deadlines

        # Reference date in early October - should see Q1 deadline
        deadlines = get_upcoming_deadlines(
            frequency="quarterly",
            days_ahead=60,
            reference_date=date(2025, 10, 1),
        )
        q1 = [d for d in deadlines if "Q1" in d.get("quarter", "")]
        assert len(q1) >= 1
        assert q1[0]["due_date"] == date(2025, 10, 28)

    def test_q2_deadline(self, app):
        """Q2 (Oct-Dec) due 28 Feb (special date)."""
        from webapp.services.bas_deadlines import get_upcoming_deadlines

        deadlines = get_upcoming_deadlines(
            frequency="quarterly",
            days_ahead=120,
            reference_date=date(2026, 1, 1),
        )
        q2 = [d for d in deadlines if "Q2" in d.get("quarter", "")]
        assert len(q2) >= 1
        assert q2[0]["due_date"] == date(2026, 2, 28)

    def test_q3_deadline(self, app):
        """Q3 (Jan-Mar) due 28 Apr."""
        from webapp.services.bas_deadlines import get_upcoming_deadlines

        deadlines = get_upcoming_deadlines(
            frequency="quarterly",
            days_ahead=60,
            reference_date=date(2026, 4, 1),
        )
        q3 = [d for d in deadlines if "Q3" in d.get("quarter", "")]
        assert len(q3) >= 1
        assert q3[0]["due_date"] == date(2026, 4, 28)

    def test_q4_deadline(self, app):
        """Q4 (Apr-Jun) due 28 Jul."""
        from webapp.services.bas_deadlines import get_upcoming_deadlines

        # Use a date before the Q4 deadline (28 Jul) within the same FY
        deadlines = get_upcoming_deadlines(
            frequency="quarterly",
            days_ahead=60,
            reference_date=date(2025, 7, 1),
        )
        q4 = [d for d in deadlines if "Q4" in d.get("quarter", "")]
        assert len(q4) >= 1
        assert q4[0]["due_date"] == date(2025, 7, 28)


class TestMonthlyDeadlines:
    """Test monthly BAS deadline calculations."""

    def test_monthly_due_21st(self, app):
        """Monthly BAS due on 21st of following month."""
        from webapp.services.bas_deadlines import get_upcoming_deadlines

        deadlines = get_upcoming_deadlines(
            frequency="monthly",
            days_ahead=60,
            reference_date=date(2026, 1, 15),
        )
        assert len(deadlines) > 0
        # January BAS should be due 21 Feb
        jan = [d for d in deadlines if d["due_date"] == date(2026, 2, 21)]
        assert len(jan) >= 1

    def test_december_monthly(self, app):
        """December monthly BAS due 21 Jan next year."""
        from webapp.services.bas_deadlines import _get_monthly_deadline

        due = _get_monthly_deadline(2025, 12)
        assert due == date(2026, 1, 21)


class TestNextDeadline:
    """Test get_next_deadline function."""

    def test_next_deadline_returns_upcoming(self, app):
        """Test that next deadline returns the soonest upcoming deadline."""
        from webapp.services.bas_deadlines import get_next_deadline

        result = get_next_deadline(
            frequency="quarterly",
            reference_date=date(2025, 10, 1),
        )
        assert result is not None
        assert result["days_remaining"] >= 0

    def test_next_deadline_with_overdue(self, app):
        """Test next deadline when one is overdue."""
        from webapp.services.bas_deadlines import get_next_deadline

        # Day after Q1 deadline - should find Q2 as next
        result = get_next_deadline(
            frequency="quarterly",
            reference_date=date(2025, 10, 29),
        )
        assert result is not None


class TestDeadlineStatus:
    """Test deadline status function."""

    def test_status_due_soon(self, app):
        """Test 'due_soon' status when within 7 days."""
        from webapp.services.bas_deadlines import get_deadline_status

        status = get_deadline_status(
            frequency="quarterly",
            reference_date=date(2025, 10, 25),  # 3 days before 28 Oct
        )
        assert status == "due_soon"

    def test_status_upcoming(self, app):
        """Test 'upcoming' status when within 30 days."""
        from webapp.services.bas_deadlines import get_deadline_status

        status = get_deadline_status(
            frequency="quarterly",
            reference_date=date(2025, 10, 10),  # 18 days before 28 Oct
        )
        assert status == "upcoming"

    def test_status_clear(self, app):
        """Test 'clear' status when deadline is far away."""
        from webapp.services.bas_deadlines import get_deadline_status

        status = get_deadline_status(
            frequency="quarterly",
            reference_date=date(2025, 8, 1),  # ~3 months before 28 Oct
        )
        assert status in ("clear", "upcoming")


class TestBASContextForPrompt:
    """Test BAS deadline context for AI system prompt injection."""

    def test_context_when_due_soon(self, app):
        """Test that context is returned when deadline is within 14 days."""
        from webapp.models import User, db

        user = User(
            email="test@test.com",
            password_hash="hash",
            name="Test",
            role="owner",
            bas_frequency="quarterly",
            bas_reminders_enabled=True,
        )
        db.session.add(user)
        db.session.commit()

        from webapp.services.bas_deadlines import get_bas_context_for_prompt

        context = get_bas_context_for_prompt(
            user.id,
            reference_date=date(2025, 10, 20),  # 8 days before 28 Oct
        )
        assert context is not None
        assert "due in" in context

    def test_no_context_when_far_away(self, app):
        """Test that no context is returned when deadline is far away."""
        from webapp.models import User, db

        user = User(
            email="test@test.com",
            password_hash="hash",
            name="Test",
            role="owner",
            bas_frequency="quarterly",
            bas_reminders_enabled=True,
        )
        db.session.add(user)
        db.session.commit()

        from webapp.services.bas_deadlines import get_bas_context_for_prompt

        context = get_bas_context_for_prompt(
            user.id,
            reference_date=date(2025, 8, 1),
        )
        assert context is None

    def test_no_context_for_unknown_user(self, app):
        """Test no context for nonexistent user."""
        from webapp.services.bas_deadlines import get_bas_context_for_prompt

        context = get_bas_context_for_prompt("nonexistent-id")
        assert context is None


class TestRemindersBlueprint:
    """Test the reminders API endpoints."""

    def test_get_reminders(self, app):
        """Test getting BAS reminders."""
        client = app.test_client()
        client.post(
            "/api/auth/register",
            json={"email": "test@test.com", "password": "password123", "name": "Test"},
        )
        res = client.get("/api/reminders/bas")
        assert res.status_code == 200
        data = res.get_json()
        assert "reminders" in data
        assert "status" in data

    def test_get_settings(self, app):
        """Test getting reminder settings."""
        client = app.test_client()
        client.post(
            "/api/auth/register",
            json={"email": "test@test.com", "password": "password123", "name": "Test"},
        )
        res = client.get("/api/reminders/settings")
        assert res.status_code == 200
        data = res.get_json()
        assert data["settings"]["bas_frequency"] == "quarterly"
        assert data["settings"]["bas_reminders_enabled"] is True

    def test_update_settings(self, app):
        """Test updating reminder settings."""
        client = app.test_client()
        client.post(
            "/api/auth/register",
            json={"email": "test@test.com", "password": "password123", "name": "Test"},
        )
        res = client.put(
            "/api/reminders/settings",
            json={"bas_frequency": "monthly", "bas_reminders_enabled": False},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["settings"]["bas_frequency"] == "monthly"
        assert data["settings"]["bas_reminders_enabled"] is False

    def test_update_settings_invalid_frequency(self, app):
        """Test updating with invalid frequency."""
        client = app.test_client()
        client.post(
            "/api/auth/register",
            json={"email": "test@test.com", "password": "password123", "name": "Test"},
        )
        res = client.put(
            "/api/reminders/settings",
            json={"bas_frequency": "weekly"},
        )
        assert res.status_code == 400
