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


def _set_xero_session(client, tenant_id, tenant_name):
    """Set Xero connection in session for a logged-in client."""
    with client.session_transaction() as sess:
        sess["xero_connection"] = {
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "access_token": "fake-token",
        }
        sess["xero_tenants"] = [
            {"tenant_id": tenant_id, "tenant_name": tenant_name},
        ]


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
        from webapp.models import Team

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


class TestPerClientChecklists:
    """Tests for per-tenant (per-client) checklist isolation."""

    def test_different_tenants_have_separate_progress(self, app, db):
        """Test that two tenants have independent checklist progress."""
        from webapp.models import Team

        team = Team(name="Test Team", owner_id="owner-1")
        db.session.add(team)
        db.session.commit()

        from webapp.services.readiness_checks import (
            get_current_checklist,
            save_checklist_progress,
        )

        # Tenant A: bank_rec done
        save_checklist_progress(
            team_id=team.id,
            user_id="user-1",
            checklist_type="month_end",
            period="2026-01",
            items=[{"key": "bank_rec", "completed": True}],
            tenant_id="tenant-a",
            tenant_name="Acme Pty Ltd",
        )

        # Tenant B: bank_rec not done
        save_checklist_progress(
            team_id=team.id,
            user_id="user-1",
            checklist_type="month_end",
            period="2026-01",
            items=[{"key": "bank_rec", "completed": False}],
            tenant_id="tenant-b",
            tenant_name="Beta Corp",
        )

        # Load tenant A
        result_a = get_current_checklist(
            team.id, reference_date=date(2026, 1, 15), tenant_id="tenant-a"
        )
        bank_a = [i for i in result_a["items"] if i["key"] == "bank_rec"][0]
        assert bank_a["completed"] is True
        assert result_a["tenant_id"] == "tenant-a"

        # Load tenant B
        result_b = get_current_checklist(
            team.id, reference_date=date(2026, 1, 15), tenant_id="tenant-b"
        )
        bank_b = [i for i in result_b["items"] if i["key"] == "bank_rec"][0]
        assert bank_b["completed"] is False
        assert result_b["tenant_id"] == "tenant-b"

    def test_no_tenant_loads_null_tenant_progress(self, app, db):
        """Progress saved without tenant is isolated from tenant progress."""
        from webapp.models import Team

        team = Team(name="Test Team", owner_id="owner-1")
        db.session.add(team)
        db.session.commit()

        from webapp.services.readiness_checks import (
            get_current_checklist,
            save_checklist_progress,
        )

        save_checklist_progress(
            team_id=team.id,
            user_id="user-1",
            checklist_type="month_end",
            period="2026-01",
            items=[{"key": "bank_rec", "completed": True}],
        )

        # Without tenant should find the null-tenant record
        result = get_current_checklist(
            team.id, reference_date=date(2026, 1, 15)
        )
        bank = [i for i in result["items"] if i["key"] == "bank_rec"][0]
        assert bank["completed"] is True

        # With tenant should NOT find the null-tenant record
        result_t = get_current_checklist(
            team.id, reference_date=date(2026, 1, 15), tenant_id="tenant-x"
        )
        bank_t = [i for i in result_t["items"] if i["key"] == "bank_rec"][0]
        assert bank_t["completed"] is False

    def test_history_filtered_by_tenant(self, app, db):
        """Test that history can be filtered by tenant_id."""
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
            tenant_id="tenant-a",
        )
        save_checklist_progress(
            team_id=team.id,
            user_id="user-1",
            checklist_type="month_end",
            period="2025-12",
            items=[{"key": "bank_rec", "completed": False}],
            tenant_id="tenant-b",
        )

        history_a = get_checklist_history(team.id, tenant_id="tenant-a")
        assert len(history_a) == 1
        assert history_a[0]["tenant_id"] == "tenant-a"

    def test_checklist_progress_id_returned(self, app, db):
        """Test that checklist_progress_id is returned after save."""
        from webapp.models import Team

        team = Team(name="Test Team", owner_id="owner-1")
        db.session.add(team)
        db.session.commit()

        from webapp.services.readiness_checks import (
            get_current_checklist,
            save_checklist_progress,
        )

        save_checklist_progress(
            team_id=team.id,
            user_id="user-1",
            checklist_type="month_end",
            period="2026-01",
            items=[{"key": "bank_rec", "completed": True}],
        )

        result = get_current_checklist(
            team.id, reference_date=date(2026, 1, 15)
        )
        assert result["checklist_progress_id"] is not None

    def test_to_dict_includes_tenant_fields(self, app, db):
        """Test that to_dict includes tenant_id and tenant_name."""
        from webapp.models import Team

        team = Team(name="Test Team", owner_id="owner-1")
        db.session.add(team)
        db.session.commit()

        from webapp.services.readiness_checks import save_checklist_progress

        progress = save_checklist_progress(
            team_id=team.id,
            user_id="user-1",
            checklist_type="month_end",
            period="2026-01",
            items=[{"key": "bank_rec", "completed": True}],
            tenant_id="tenant-z",
            tenant_name="Zeta Inc",
        )
        d = progress.to_dict()
        assert d["tenant_id"] == "tenant-z"
        assert d["tenant_name"] == "Zeta Inc"


class TestChecklistComments:
    """Tests for comment CRUD on checklist items."""

    def _create_progress(self, db):
        """Helper to create a team + progress record."""
        from webapp.models import Team, User

        team = Team(name="Test Team", owner_id="owner-1")
        db.session.add(team)
        db.session.flush()

        user = User(
            email="commenter@test.com",
            password_hash="fakehash",
            name="Commenter",
            team_id=team.id,
        )
        db.session.add(user)
        db.session.flush()

        from webapp.services.readiness_checks import save_checklist_progress

        progress = save_checklist_progress(
            team_id=team.id,
            user_id=user.id,
            checklist_type="month_end",
            period="2026-01",
            items=[{"key": "bank_rec", "completed": False}],
        )
        return team, user, progress

    def test_add_comment(self, app, db):
        """Test adding a comment to a checklist item."""
        _, user, progress = self._create_progress(db)

        from webapp.services.readiness_checks import add_checklist_comment

        comment = add_checklist_comment(
            checklist_progress_id=progress.id,
            item_key="bank_rec",
            user_id=user.id,
            content="Need to chase bank statement",
        )
        assert comment.id is not None
        assert comment.item_key == "bank_rec"
        assert comment.content == "Need to chase bank statement"

    def test_comment_html_escaped(self, app, db):
        """Test that comment content is HTML-escaped."""
        _, user, progress = self._create_progress(db)

        from webapp.services.readiness_checks import add_checklist_comment

        comment = add_checklist_comment(
            checklist_progress_id=progress.id,
            item_key="bank_rec",
            user_id=user.id,
            content="<script>alert('xss')</script>",
        )
        assert "<script>" not in comment.content
        assert "&lt;script&gt;" in comment.content

    def test_comment_empty_rejected(self, app, db):
        """Test that empty comment is rejected."""
        _, user, progress = self._create_progress(db)

        from webapp.services.readiness_checks import add_checklist_comment

        with pytest.raises(ValueError, match="cannot be empty"):
            add_checklist_comment(
                checklist_progress_id=progress.id,
                item_key="bank_rec",
                user_id=user.id,
                content="   ",
            )

    def test_comment_invalid_item_key(self, app, db):
        """Test that invalid item_key is rejected."""
        _, user, progress = self._create_progress(db)

        from webapp.services.readiness_checks import add_checklist_comment

        with pytest.raises(ValueError, match="Invalid item_key"):
            add_checklist_comment(
                checklist_progress_id=progress.id,
                item_key="nonexistent_key",
                user_id=user.id,
                content="Test",
            )

    def test_comment_truncated_at_max_length(self, app, db):
        """Test that very long comments are truncated."""
        _, user, progress = self._create_progress(db)

        from webapp.services.readiness_checks import add_checklist_comment

        long_content = "x" * 3000
        comment = add_checklist_comment(
            checklist_progress_id=progress.id,
            item_key="bank_rec",
            user_id=user.id,
            content=long_content,
        )
        assert len(comment.content) <= 2000

    def test_get_comments_grouped(self, app, db):
        """Test that comments are returned grouped by item_key."""
        _, user, progress = self._create_progress(db)

        from webapp.services.readiness_checks import (
            add_checklist_comment,
            get_checklist_comments,
        )

        add_checklist_comment(
            checklist_progress_id=progress.id,
            item_key="bank_rec",
            user_id=user.id,
            content="Note 1",
        )
        add_checklist_comment(
            checklist_progress_id=progress.id,
            item_key="bank_rec",
            user_id=user.id,
            content="Note 2",
        )
        add_checklist_comment(
            checklist_progress_id=progress.id,
            item_key="gst_rec",
            user_id=user.id,
            content="GST note",
        )

        grouped = get_checklist_comments(progress.id)
        assert len(grouped["bank_rec"]) == 2
        assert len(grouped["gst_rec"]) == 1

    def test_comment_with_assignment(self, app, db):
        """Test adding a comment with teammate assignment."""
        team, user, progress = self._create_progress(db)
        from webapp.models import User as UserModel

        teammate = UserModel(
            email="teammate@test.com",
            password_hash="fakehash",
            name="Teammate",
            team_id=team.id,
        )
        db.session.add(teammate)
        db.session.commit()

        from webapp.services.readiness_checks import add_checklist_comment

        comment = add_checklist_comment(
            checklist_progress_id=progress.id,
            item_key="bank_rec",
            user_id=user.id,
            content="Please handle this",
            assigned_to=teammate.id,
        )
        assert comment.assigned_to == teammate.id
        d = comment.to_dict()
        assert d["assignee_name"] == "Teammate"
        assert d["author_name"] == "Commenter"

    def test_comment_to_dict(self, app, db):
        """Test comment to_dict includes all expected fields."""
        _, user, progress = self._create_progress(db)

        from webapp.services.readiness_checks import add_checklist_comment

        comment = add_checklist_comment(
            checklist_progress_id=progress.id,
            item_key="bank_rec",
            user_id=user.id,
            content="Test note",
        )
        d = comment.to_dict()
        assert "id" in d
        assert "checklist_progress_id" in d
        assert "item_key" in d
        assert "content" in d
        assert "author_name" in d
        assert "created_at" in d


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

    def test_get_checklist_includes_tenant_fields(self, client, db):
        """Test that checklist response includes tenant fields."""
        _register(client)
        _set_xero_session(client, "t-123", "Acme Pty Ltd")
        res = client.get("/api/readiness/checklist")
        assert res.status_code == 200
        data = res.get_json()
        assert data["checklist"]["tenant_id"] == "t-123"
        assert data["checklist"]["tenant_name"] == "Acme Pty Ltd"

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

    def test_team_members_endpoint(self, client, db):
        """Test team members endpoint."""
        _register(client)
        res = client.get("/api/readiness/team-members")
        assert res.status_code == 200
        data = res.get_json()
        assert "members" in data
        assert len(data["members"]) >= 1  # At least the registered user

    def test_comments_post_requires_progress_id(self, client, db):
        """Test that POST comment requires checklist_progress_id."""
        _register(client)
        res = client.post(
            "/api/readiness/comments",
            json={"item_key": "bank_rec", "content": "test"},
        )
        assert res.status_code == 400

    def test_comments_get_requires_progress_id(self, client, db):
        """Test that GET comments requires checklist_progress_id."""
        _register(client)
        res = client.get("/api/readiness/comments")
        assert res.status_code == 400

    def test_comments_round_trip(self, client, db):
        """Test creating and retrieving a comment via API."""
        _register(client)

        # Create checklist progress first
        res = client.get("/api/readiness/checklist")
        checklist = res.get_json()["checklist"]

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
        progress_id = res.get_json()["progress"]["id"]

        # Post a comment
        res = client.post(
            "/api/readiness/comments",
            json={
                "checklist_progress_id": progress_id,
                "item_key": "bank_rec",
                "content": "Need to follow up with bank",
            },
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert data["comment"]["item_key"] == "bank_rec"

        # Get comments
        res = client.get(
            f"/api/readiness/comments?checklist_progress_id={progress_id}"
        )
        assert res.status_code == 200
        comments = res.get_json()["comments"]
        assert "bank_rec" in comments
        assert len(comments["bank_rec"]) == 1

    def test_comment_idor_protection(self, client, db):
        """Test that comment API rejects checklist not owned by user's team."""
        _register(client)
        # Try a fake checklist_progress_id
        res = client.post(
            "/api/readiness/comments",
            json={
                "checklist_progress_id": "nonexistent-id",
                "item_key": "bank_rec",
                "content": "test",
            },
        )
        assert res.status_code == 404
