"""Tests for skill analytics service."""

from datetime import timedelta

import pytest

from webapp.app import create_app
from webapp.config import TestingConfig
from webapp.models import SkillUsage, db
from webapp.skills.analytics_service import (
    SkillAnalyticsService,
    get_analytics_service,
    init_analytics_service,
)
from webapp.time_utils import utcnow


class TestSkillAnalyticsService:
    """Tests for SkillAnalyticsService class."""

    @pytest.fixture
    def app(self):
        """Create test app."""
        app = create_app(TestingConfig)
        with app.app_context():
            db.create_all()
        yield app
        with app.app_context():
            db.drop_all()

    @pytest.fixture
    def service(self, app):
        """Create analytics service."""
        with app.app_context():
            return SkillAnalyticsService()

    def test_log_usage(self, app, service):
        """Test logging skill usage."""
        with app.app_context():
            usage = service.log_usage(
                skill_name="tax_agent",
                skill_source="public",
                user_id="user-123",
                trigger="tax advice",
                confidence=0.95,
            )

            assert usage.id is not None
            assert usage.skill_name == "tax_agent"
            assert usage.skill_source == "public"
            assert usage.user_id == "user-123"
            assert usage.trigger == "tax advice"
            assert usage.confidence == 0.95

    def test_log_usage_with_team(self, app, service):
        """Test logging usage with team context."""
        with app.app_context():
            usage = service.log_usage(
                skill_name="accountant",
                skill_source="shared",
                user_id="user-123",
                team_id="team-abc",
                trigger="balance sheet",
            )

            assert usage.team_id == "team-abc"

    def test_get_top_skills(self, app, service):
        """Test getting top skills."""
        with app.app_context():
            # Create usage data
            for _ in range(5):
                service.log_usage("tax_agent", "public", "user-1")
            for _ in range(3):
                service.log_usage("accountant", "public", "user-1")
            for _ in range(1):
                service.log_usage("bas_review", "public", "user-1")

            top_skills = service.get_top_skills(period_days=30, limit=10)

            assert len(top_skills) == 3
            assert top_skills[0]["skill_name"] == "tax_agent"
            assert top_skills[0]["usage_count"] == 5
            assert top_skills[1]["skill_name"] == "accountant"
            assert top_skills[1]["usage_count"] == 3

    def test_get_top_skills_by_user(self, app, service):
        """Test getting top skills filtered by user."""
        with app.app_context():
            service.log_usage("tax_agent", "public", "user-1")
            service.log_usage("tax_agent", "public", "user-1")
            service.log_usage("accountant", "public", "user-2")

            top_skills = service.get_top_skills(user_id="user-1")

            assert len(top_skills) == 1
            assert top_skills[0]["skill_name"] == "tax_agent"
            assert top_skills[0]["usage_count"] == 2

    def test_get_top_skills_period_filter(self, app, service):
        """Test that period filter works."""
        with app.app_context():
            # Create old usage (outside period)
            old_usage = SkillUsage(
                skill_name="old_skill",
                skill_source="public",
                user_id="user-1",
            )
            old_usage.created_at = utcnow() - timedelta(days=60)
            db.session.add(old_usage)

            # Create recent usage
            service.log_usage("new_skill", "public", "user-1")
            db.session.commit()

            top_skills = service.get_top_skills(period_days=30)

            skill_names = [s["skill_name"] for s in top_skills]
            assert "new_skill" in skill_names
            assert "old_skill" not in skill_names

    def test_get_user_stats(self, app, service):
        """Test getting user statistics."""
        with app.app_context():
            service.log_usage("tax_agent", "public", "user-123")
            service.log_usage("tax_agent", "public", "user-123")
            service.log_usage("accountant", "private", "user-123")

            stats = service.get_user_stats("user-123")

            assert stats["user_id"] == "user-123"
            assert stats["total_usages"] == 3
            assert stats["skills_used"] == 2
            assert len(stats["top_skills"]) >= 1
            assert "by_source" in stats
            assert stats["by_source"]["public"] == 2
            assert stats["by_source"]["private"] == 1

    def test_get_user_stats_recent_activity(self, app, service):
        """Test user stats includes recent activity."""
        with app.app_context():
            service.log_usage("tax_agent", "public", "user-123")

            stats = service.get_user_stats("user-123")

            assert "recent_activity" in stats
            assert stats["recent_activity"]["last_7_days"] == 1

    def test_get_skill_stats(self, app, service):
        """Test getting statistics for a specific skill."""
        with app.app_context():
            service.log_usage("tax_agent", "public", "user-1", trigger="tax advice")
            service.log_usage("tax_agent", "public", "user-2", trigger="tax advice")
            service.log_usage("tax_agent", "public", "user-1", trigger="ATO")

            stats = service.get_skill_stats("tax_agent")

            assert stats["skill_name"] == "tax_agent"
            assert stats["total_usages"] == 3
            assert stats["unique_users"] == 2
            assert "usage_trend" in stats
            assert "top_triggers" in stats

    def test_get_summary(self, app, service):
        """Test getting overall usage summary."""
        with app.app_context():
            service.log_usage("tax_agent", "public", "user-1")
            service.log_usage("accountant", "private", "user-2")

            summary = service.get_summary(period_days=30)

            assert summary["total_usages"] == 2
            assert summary["active_skills"] == 2
            assert summary["active_users"] == 2
            assert "by_source" in summary


class TestAnalyticsEndpoints:
    """Tests for analytics API endpoints."""

    @pytest.fixture
    def app(self):
        """Create test app."""
        app = create_app(TestingConfig)
        with app.app_context():
            db.create_all()
        yield app
        with app.app_context():
            db.drop_all()

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return app.test_client()

    def test_get_skill_analytics(self, client):
        """Test GET /api/analytics/skills endpoint."""
        response = client.get("/api/analytics/skills")

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "top_skills" in data
        assert "period_days" in data

    def test_get_skill_analytics_with_params(self, client):
        """Test skill analytics with query params."""
        response = client.get("/api/analytics/skills?period=7&limit=5")

        assert response.status_code == 200
        data = response.get_json()
        assert data["period_days"] == 7

    def test_get_user_skill_stats(self, client, app):
        """Test GET /api/analytics/skills/user/<id> endpoint."""
        with app.app_context():
            service = get_analytics_service()
            service.log_usage("tax_agent", "public", "user-123")

        response = client.get("/api/analytics/skills/user/user-123")

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "stats" in data

    def test_get_skill_detail_stats(self, client, app):
        """Test GET /api/analytics/skills/<name> endpoint."""
        with app.app_context():
            service = get_analytics_service()
            service.log_usage("tax_agent", "public", "user-123")

        response = client.get("/api/analytics/skills/tax_agent")

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["stats"]["skill_name"] == "tax_agent"

    def test_get_analytics_summary(self, client):
        """Test GET /api/analytics/summary endpoint."""
        response = client.get("/api/analytics/summary")

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "summary" in data


class TestAnalyticsServiceInit:
    """Tests for analytics service initialization."""

    def test_init_analytics_service(self):
        """Test analytics service initialization."""
        app = create_app(TestingConfig)

        with app.app_context():
            service = init_analytics_service(app)

            assert service is not None
            assert isinstance(service, SkillAnalyticsService)

    def test_get_analytics_service_singleton(self):
        """Test that get_analytics_service returns singleton."""
        app = create_app(TestingConfig)

        with app.app_context():
            init_analytics_service(app)

            service1 = get_analytics_service()
            service2 = get_analytics_service()

            assert service1 is service2
