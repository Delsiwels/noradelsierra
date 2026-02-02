"""Tests for readiness checks service and blueprint."""

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
def db(app):
    from webapp.models import db as _db

    return _db


def _register(client, email="test@test.com"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": "password123", "name": "Test User"},
    )


class TestChecklistGeneration:
    """Tests for checklist generation."""

    def test_month_end_checklist(self, app):
        """Test month-end checklist has expected items."""
        from webapp.services.readiness_checks import get_month_end_checklist

        items = get_month_end_checklist()
        assert len(items) > 0
        keys = [i["key"] for i in items]
        assert "bank_rec" in keys
        assert "gst_rec" in keys
        assert "payroll_rec" in keys

    def test_eofy_checklist(self, app):
        """Test EOFY checklist has expected items."""
        from webapp.services.readiness_checks import get_eofy_checklist

        items = get_eofy_checklist()
        assert len(items) > 0
        keys = [i["key"] for i in items]
        assert "stp_final" in keys
        assert "super_guarantee" in keys
        assert "stocktake" in keys

    def test_all_items_start_uncompleted(self, app):
        """Test all checklist items start as not completed."""
        from webapp.services.readiness_checks import get_month_end_checklist

        items = get_month_end_checklist()
        for item in items:
            assert item["completed"] is False


class TestContextAwareChecklist:
    """Test context-aware checklist selection."""

    def test_eofy_in_june(self, app, db):
        """Test EOFY checklist returned in June."""
        from webapp.models import Team, User

        team = Team(name="Test Team", owner_id="owner-1")
        db.session.add(team)
        db.session.commit()

        from webapp.services.readiness_checks import get_current_checklist

        result = get_current_checklist(team.id, reference_date=date(2026, 6, 15))
        assert result["checklist_type"] == "eofy"

    def test_eofy_in_may(self, app, db):
        """Test EOFY checklist returned in May."""
        from webapp.models import Team

        team = Team(name="Test Team", owner_id="owner-1")
        db.session.add(team)
        db.session.commit()

        from webapp.services.readiness_checks import get_current_checklist

        result = get_current_checklist(team.id, reference_date=date(2026, 5, 1))
        assert result["checklist_type"] == "eofy"

    def test_eofy_in_july(self, app, db):
        """Test EOFY checklist returned in July (for wrap-up)."""
        from webapp.models import Team

        team = Team(name="Test Team", owner_id="owner-1")
        db.session.add(team)
        db.session.commit()

        from webapp.services.readiness_checks import get_current_checklist

        result = get_current_checklist(team.id, reference_date=date(2026, 7, 10))
        assert result["checklist_type"] == "eofy"

    def test_month_end_in_january(self, app, db):
        """Test month-end checklist returned in January."""
        from webapp.models import Team

        team = Team(name="Test Team", owner_id="owner-1")
        db.session.add(team)
        db.session.commit()

        from webapp.services.readiness_checks import get_current_checklist

        result = get_current_checklist(team.id, reference_date=date(2026, 1, 15))
        assert result["checklist_type"] == "month_end"

    def test_month_end_in_november(self, app, db):
        """Test month-end checklist in November."""
        from webapp.models import Team

        team = Team(name="Test Team", owner_id="owner-1")
        db.session.add(team)
        db.session.commit()

        from webapp.services.readiness_checks import get_current_checklist

        result = get_current_checklist(team.id, reference_date=date(2025, 11, 20))
        assert result["checklist_type"] == "month_end"


class TestChecklistProgress:
    """Test saving and loading checklist progress."""

    def test_save_progress(self, app, db):
        """Test saving checklist progress."""
        from webapp.models import Team

        team = Team(name="Test Team", owner_id="owner-1")
        db.session.add(team)
        db.session.commit()

        from webapp.services.readiness_checks import save_checklist_progress

        items = [
            {"key": "bank_rec", "label": "Bank rec", "completed": True},
            {"key": "gst_rec", "label": "GST rec", "completed": False},
        ]
        progress = save_checklist_progress(
            team_id=team.id,
            user_id="user-1",
            checklist_type="month_end",
            period="2026-01",
            items=items,
        )
        assert progress.id is not None
        assert progress.completed_at is None  # Not all items complete

    def test_save_all_complete_sets_completed_at(self, app, db):
        """Test that completing all items sets completed_at."""
        from webapp.models import Team

        team = Team(name="Test Team", owner_id="owner-1")
        db.session.add(team)
        db.session.commit()

        from webapp.services.readiness_checks import save_checklist_progress

        items = [
            {"key": "bank_rec", "label": "Bank rec", "completed": True},
            {"key": "gst_rec", "label": "GST rec", "completed": True},
        ]
        progress = save_checklist_progress(
            team_id=team.id,
            user_id="user-1",
            checklist_type="month_end",
            period="2026-01",
            items=items,
        )
        assert progress.completed_at is not None

    def test_load_saved_progress(self, app, db):
        """Test that saved progress is loaded into checklist."""
        from webapp.models import Team

        team = Team(name="Test Team", owner_id="owner-1")
        db.session.add(team)
        db.session.commit()

        from webapp.services.readiness_checks import (
            get_current_checklist,
            save_checklist_progress,
        )

        # Save some progress
        items = [{"key": "bank_rec", "label": "Bank rec", "completed": True}]
        save_checklist_progress(
            team_id=team.id,
            user_id="user-1",
            checklist_type="month_end",
            period="2026-01",
            items=items,
        )

        # Load and verify
        result = get_current_checklist(team.id, reference_date=date(2026, 1, 15))
        bank_rec = [i for i in result["items"] if i["key"] == "bank_rec"]
        assert len(bank_rec) == 1
        assert bank_rec[0]["completed"] is True

    def test_checklist_history(self, app, db):
        """Test getting checklist history."""
        from webapp.models import Team

        team = Team(name="Test Team", owner_id="owner-1")
        db.session.add(team)
        db.session.commit()

        from webapp.services.readiness_checks import (
            get_checklist_history,
            save_checklist_progress,
        )

        save_checklist_progress(
            team_id=team.id,
            user_id="user-1",
            checklist_type="month_end",
            period="2025-12",
            items=[{"key": "bank_rec", "completed": True}],
        )
        save_checklist_progress(
            team_id=team.id,
            user_id="user-1",
            checklist_type="month_end",
            period="2026-01",
            items=[{"key": "bank_rec", "completed": False}],
        )

        history = get_checklist_history(team.id)
        assert len(history) == 2


class TestReadinessBlueprint:
    """Tests for readiness API endpoints."""

    def test_get_checklist(self, client, db):
        """Test getting current checklist."""
        _register(client)
        res = client.get("/api/readiness/checklist")
        assert res.status_code == 200
        data = res.get_json()
        assert "checklist" in data
        assert data["checklist"]["total"] > 0

    def test_update_checklist(self, client, db):
        """Test updating checklist progress."""
        _register(client)

        # First get the checklist to know the period
        res = client.get("/api/readiness/checklist")
        checklist = res.get_json()["checklist"]

        # Update progress
        res = client.put(
            "/api/readiness/checklist",
            json={
                "checklist_type": checklist["checklist_type"],
                "period": checklist["period"],
                "items": [
                    {"key": "bank_rec", "label": "Bank rec", "completed": True},
                ],
            },
        )
        assert res.status_code == 200
        assert res.get_json()["success"] is True

    def test_update_invalid_type(self, client, db):
        """Test update with invalid checklist type."""
        _register(client)
        res = client.put(
            "/api/readiness/checklist",
            json={
                "checklist_type": "invalid",
                "period": "2026-01",
                "items": [],
            },
        )
        assert res.status_code == 400

    def test_get_history(self, client, db):
        """Test getting checklist history."""
        _register(client)
        res = client.get("/api/readiness/history")
        assert res.status_code == 200
        assert "history" in res.get_json()

    def test_get_status(self, client, db):
        """Test getting quick status."""
        _register(client)
        res = client.get("/api/readiness/status")
        assert res.status_code == 200
        data = res.get_json()
        assert "completed" in data
        assert "total" in data

    def test_checklist_page(self, client):
        """Test checklist page renders."""
        _register(client)
        res = client.get("/readiness")
        assert res.status_code == 200

    def test_history_page(self, client):
        """Test history page renders."""
        _register(client)
        res = client.get("/readiness/history")
        assert res.status_code == 200
