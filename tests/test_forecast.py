"""Tests for cash flow forecast blueprint and agent BAS deadlines."""

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


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(app):
    """Client with a registered & logged-in user."""
    c = app.test_client()
    c.post(
        "/api/auth/register",
        json={"email": "forecast@test.com", "password": "password123", "name": "Test"},
    )
    return c


# =========================================================================
# Agent BAS deadline tests
# =========================================================================


class TestAgentDeadlines:
    """Test agent-lodged BAS deadline dates."""

    def test_agent_q1_deadline(self, app):
        """Agent Q1 (Jul-Sep) due 25 Nov (vs self-lodge 28 Oct)."""
        from webapp.services.bas_deadlines import get_upcoming_deadlines

        deadlines = get_upcoming_deadlines(
            frequency="quarterly",
            days_ahead=90,
            reference_date=date(2025, 10, 1),
            lodge_method="agent",
        )
        q1 = [d for d in deadlines if "Q1" in d.get("quarter", "")]
        assert len(q1) >= 1
        assert q1[0]["due_date"] == date(2025, 11, 25)

    def test_agent_q3_deadline(self, app):
        """Agent Q3 (Jan-Mar) due 26 May (vs self-lodge 28 Apr)."""
        from webapp.services.bas_deadlines import get_upcoming_deadlines

        deadlines = get_upcoming_deadlines(
            frequency="quarterly",
            days_ahead=90,
            reference_date=date(2026, 4, 1),
            lodge_method="agent",
        )
        q3 = [d for d in deadlines if "Q3" in d.get("quarter", "")]
        assert len(q3) >= 1
        assert q3[0]["due_date"] == date(2026, 5, 26)

    def test_agent_q4_deadline(self, app):
        """Agent Q4 (Apr-Jun) due 25 Aug (vs self-lodge 28 Jul)."""
        from webapp.services.bas_deadlines import get_upcoming_deadlines

        deadlines = get_upcoming_deadlines(
            frequency="quarterly",
            days_ahead=90,
            reference_date=date(2025, 7, 1),
            lodge_method="agent",
        )
        q4 = [d for d in deadlines if "Q4" in d.get("quarter", "")]
        assert len(q4) >= 1
        assert q4[0]["due_date"] == date(2025, 8, 25)

    def test_agent_q2_same_as_self(self, app):
        """Agent Q2 (Oct-Dec) due 28 Feb, same as self-lodge."""
        from webapp.services.bas_deadlines import get_upcoming_deadlines

        agent = get_upcoming_deadlines(
            frequency="quarterly",
            days_ahead=120,
            reference_date=date(2026, 1, 1),
            lodge_method="agent",
        )
        self_dl = get_upcoming_deadlines(
            frequency="quarterly",
            days_ahead=120,
            reference_date=date(2026, 1, 1),
            lodge_method="self",
        )
        q2_agent = [d for d in agent if "Q2" in d.get("quarter", "")]
        q2_self = [d for d in self_dl if "Q2" in d.get("quarter", "")]
        assert q2_agent[0]["due_date"] == q2_self[0]["due_date"]
        assert q2_agent[0]["due_date"] == date(2026, 2, 28)

    def test_self_lodge_default(self, app):
        """Default lodge_method is 'self'."""
        from webapp.services.bas_deadlines import get_upcoming_deadlines

        deadlines = get_upcoming_deadlines(
            frequency="quarterly",
            days_ahead=90,
            reference_date=date(2025, 10, 1),
        )
        q1 = [d for d in deadlines if "Q1" in d.get("quarter", "")]
        assert q1[0]["due_date"] == date(2025, 10, 28)

    def test_agent_differs_from_self(self, app):
        """Agent Q1 date differs from self-lodge Q1 date."""
        from webapp.services.bas_deadlines import get_upcoming_deadlines

        agent = get_upcoming_deadlines(
            frequency="quarterly",
            days_ahead=90,
            reference_date=date(2025, 10, 1),
            lodge_method="agent",
        )
        self_dl = get_upcoming_deadlines(
            frequency="quarterly",
            days_ahead=90,
            reference_date=date(2025, 10, 1),
            lodge_method="self",
        )
        q1_agent = [d for d in agent if "Q1" in d.get("quarter", "")]
        q1_self = [d for d in self_dl if "Q1" in d.get("quarter", "")]
        assert q1_agent[0]["due_date"] != q1_self[0]["due_date"]


class TestGetDeadlinesForForecast:
    """Test the forecast-specific deadline function."""

    def test_returns_multiple_deadlines(self, app):
        """Should return several deadlines for a 12-month window."""
        from webapp.services.bas_deadlines import get_deadlines_for_forecast

        deadlines = get_deadlines_for_forecast(
            frequency="quarterly",
            lodge_method="self",
            months_ahead=12,
            reference_date=date(2026, 2, 1),
        )
        assert len(deadlines) >= 3

    def test_agent_deadlines_in_forecast(self, app):
        """Agent deadlines should use agent dates."""
        from webapp.services.bas_deadlines import get_deadlines_for_forecast

        deadlines = get_deadlines_for_forecast(
            frequency="quarterly",
            lodge_method="agent",
            months_ahead=12,
            reference_date=date(2026, 2, 1),
        )
        dates = [d["due_date"] for d in deadlines]
        # Q3 agent due 26 May 2026 should be in the list
        assert date(2026, 5, 26) in dates


# =========================================================================
# Forecast page & API endpoint tests
# =========================================================================


class TestForecastPage:
    """Test the forecast page route."""

    def test_page_loads(self, auth_client):
        """GET /cash-flow-forecast should return 200."""
        resp = auth_client.get("/cash-flow-forecast")
        assert resp.status_code == 200
        assert b"Cash Flow Forecast" in resp.data

    def test_page_contains_toggle(self, auth_client):
        """Page should contain lodge method toggle buttons."""
        resp = auth_client.get("/cash-flow-forecast")
        assert b"Self Lodge" in resp.data
        assert b"Tax Agent" in resp.data

    def test_page_contains_generate_button(self, auth_client):
        """Page should contain the generate forecast button."""
        resp = auth_client.get("/cash-flow-forecast")
        assert b"Generate Forecast" in resp.data


class TestDeadlinesAPI:
    """Test the deadlines API endpoint."""

    def test_deadlines_self(self, auth_client):
        """GET /api/forecast/deadlines?lodge_method=self returns deadlines."""
        resp = auth_client.get("/api/forecast/deadlines?lodge_method=self")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "deadlines" in data
        assert data["lodge_method"] == "self"
        assert len(data["deadlines"]) > 0

    def test_deadlines_agent(self, auth_client):
        """GET /api/forecast/deadlines?lodge_method=agent returns agent dates."""
        resp = auth_client.get("/api/forecast/deadlines?lodge_method=agent")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["lodge_method"] == "agent"
        assert len(data["deadlines"]) > 0

    def test_deadlines_invalid_method_defaults_self(self, auth_client):
        """Invalid lodge_method defaults to self."""
        resp = auth_client.get("/api/forecast/deadlines?lodge_method=invalid")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["lodge_method"] == "self"


class TestLodgeMethodAPI:
    """Test the lodge method persistence endpoint."""

    def test_set_self(self, auth_client):
        """PUT /api/forecast/lodge-method with self."""
        resp = auth_client.put(
            "/api/forecast/lodge-method",
            json={"lodge_method": "self"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["lodge_method"] == "self"

    def test_set_agent(self, auth_client):
        """PUT /api/forecast/lodge-method with agent."""
        resp = auth_client.put(
            "/api/forecast/lodge-method",
            json={"lodge_method": "agent"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["lodge_method"] == "agent"

    def test_invalid_method_rejected(self, auth_client):
        """Invalid lodge_method should return 400."""
        resp = auth_client.put(
            "/api/forecast/lodge-method",
            json={"lodge_method": "weekly"},
        )
        assert resp.status_code == 400

    def test_persists_preference(self, app, auth_client):
        """Lodge method should persist to user model."""
        auth_client.put(
            "/api/forecast/lodge-method",
            json={"lodge_method": "agent"},
        )
        from webapp.models import User

        user = User.query.filter_by(email="forecast@test.com").first()
        assert user.bas_lodge_method == "agent"


class TestGenerateForecastAPI:
    """Test the forecast generation endpoint."""

    def test_requires_xero(self, auth_client):
        """POST /api/forecast/generate without Xero session returns 400."""
        resp = auth_client.post(
            "/api/forecast/generate",
            json={"lodge_method": "self"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "Xero not connected"

    def test_cash_position_requires_xero(self, auth_client):
        """GET /api/forecast/cash-position without Xero session returns 400."""
        resp = auth_client.get("/api/forecast/cash-position")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "Xero not connected"


# =========================================================================
# User model tests
# =========================================================================


class TestUserLodgeMethod:
    """Test bas_lodge_method on User model."""

    def test_default_lodge_method(self, app):
        """Default lodge method should be 'self'."""
        from webapp.models import User, db

        user = User(
            email="model@test.com",
            password_hash="hash",
            name="Test",
            role="owner",
        )
        db.session.add(user)
        db.session.commit()
        assert user.bas_lodge_method == "self"

    def test_lodge_method_in_dict(self, app):
        """to_dict should include bas_lodge_method."""
        from webapp.models import User, db

        user = User(
            email="dict@test.com",
            password_hash="hash",
            name="Test",
            role="owner",
            bas_lodge_method="agent",
        )
        db.session.add(user)
        db.session.commit()
        d = user.to_dict()
        assert d["bas_lodge_method"] == "agent"
