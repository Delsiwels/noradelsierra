"""Tests for token usage tracking."""

import pytest

from webapp.ai.token_tracker import (
    TokenLimitExceededError,
    TokenTracker,
    get_token_tracker,
    init_token_tracker,
)
from webapp.app import create_app
from webapp.config import TestingConfig
from webapp.models import TokenUsage, db
from webapp.time_utils import utcnow


class TestTokenTracker:
    """Tests for TokenTracker class."""

    @pytest.fixture
    def app(self):
        """Create test app."""
        app = create_app(TestingConfig)
        with app.app_context():
            db.create_all()
        yield app
        with app.app_context():
            db.drop_all()

    def test_tracker_default_limit(self, app):
        """Test that tracker uses default limit from config."""
        with app.app_context():
            tracker = TokenTracker()
            assert tracker.default_limit == 100000

    def test_tracker_custom_limit(self, app):
        """Test tracker with custom limit."""
        with app.app_context():
            tracker = TokenTracker(default_limit=50000)
            assert tracker.default_limit == 50000

    def test_check_limit_new_user(self, app):
        """Test checking limit for new user."""
        with app.app_context():
            tracker = TokenTracker()

            allowed, remaining = tracker.check_limit("user-123")

            assert allowed is True
            assert remaining == 100000

    def test_record_usage_is_a_relative_db_increment(self, app):
        """A concurrent external increment must not be clobbered (#5).

        Read-modify-write would lose the external +500; a DB-level
        ``col = col + delta`` update preserves it.
        """
        from sqlalchemy import text

        with app.app_context():
            tracker = TokenTracker()
            tracker.record_usage("user-x", None, 100, 0)  # total now 100

            # Simulate another worker incrementing the same row out-of-band.
            db.session.execute(
                text(
                    "UPDATE token_usages SET total_tokens = total_tokens + 500 "
                    "WHERE user_id = 'user-x'"
                )
            )
            db.session.commit()  # DB total now 600; in-memory object still 100

            tracker.record_usage("user-x", None, 100, 0)  # +100 relative

            usage = TokenUsage.query.filter_by(user_id="user-x").first()
            assert usage.total_tokens == 700  # 100 + 500 + 100, nothing lost

    def test_reserve_then_settle_reconciles_to_actual(self, app):
        with app.app_context():
            tracker = TokenTracker(default_limit=1000)

            allowed, _remaining, reserved = tracker.reserve("u", None, estimate=400)
            assert allowed is True
            assert reserved == 400
            usage = TokenUsage.query.filter_by(user_id="u").first()
            assert usage.total_tokens == 400  # reservation applied up front

            tracker.settle("u", None, reserved, 100, 50)  # actual 150
            usage = TokenUsage.query.filter_by(user_id="u").first()
            assert usage.total_tokens == 150  # 400 - 400 + 150
            assert usage.input_tokens == 100
            assert usage.output_tokens == 50
            assert usage.request_count == 1

    def test_release_undoes_reservation(self, app):
        with app.app_context():
            tracker = TokenTracker(default_limit=1000)
            _a, _r, reserved = tracker.reserve("u2", None, estimate=400)
            tracker.release("u2", None, reserved)
            usage = TokenUsage.query.filter_by(user_id="u2").first()
            assert usage.total_tokens == 0  # reservation fully undone

    def test_reserve_bounds_concurrent_over_admission(self, app):
        """Once reservations reach the limit, further requests are blocked.

        The old check_limit would admit all three (all see total=0); reserve
        advances the counter so the third is rejected.
        """
        with app.app_context():
            tracker = TokenTracker(default_limit=500)
            a1, _r1, _res1 = tracker.reserve("u3", None, estimate=400)
            a2, _r2, _res2 = tracker.reserve("u3", None, estimate=400)
            a3, _r3, res3 = tracker.reserve("u3", None, estimate=400)
            assert a1 is True  # total 0 -> 400
            assert a2 is True  # total 400 (< 500) -> 800
            assert a3 is False  # total 800 (>= 500) -> rejected
            assert res3 == 0

    def test_reserve_noop_when_enforcement_off(self, app):
        with app.app_context():
            tracker = TokenTracker(enforce_limits=False)
            allowed, _remaining, reserved = tracker.reserve("u4", None)
            assert allowed is True
            assert reserved == 0
            assert TokenUsage.query.filter_by(user_id="u4").first() is None

    def test_record_usage(self, app):
        """Test recording token usage."""
        with app.app_context():
            tracker = TokenTracker()

            usage = tracker.record_usage("user-123", None, 100, 200)

            assert usage.input_tokens == 100
            assert usage.output_tokens == 200
            assert usage.total_tokens == 300
            assert usage.request_count == 1

    def test_record_usage_accumulates(self, app):
        """Test that usage accumulates correctly."""
        with app.app_context():
            tracker = TokenTracker()

            tracker.record_usage("user-123", None, 100, 200)
            tracker.record_usage("user-123", None, 50, 100)

            usage = TokenUsage.query.filter_by(user_id="user-123").first()

            assert usage.input_tokens == 150
            assert usage.output_tokens == 300
            assert usage.total_tokens == 450
            assert usage.request_count == 2

    def test_check_limit_with_usage(self, app):
        """Test checking limit after some usage."""
        with app.app_context():
            tracker = TokenTracker(default_limit=1000)

            tracker.record_usage("user-123", None, 300, 200)

            allowed, remaining = tracker.check_limit("user-123")

            assert allowed is True
            assert remaining == 500  # 1000 - 500

    def test_check_limit_exceeded(self, app):
        """Test that limit is enforced."""
        with app.app_context():
            tracker = TokenTracker(default_limit=1000)

            # Use up all tokens
            tracker.record_usage("user-123", None, 600, 600)

            allowed, remaining = tracker.check_limit("user-123")

            assert allowed is False
            assert remaining == 0

    def test_check_limit_disabled(self, app):
        """Test that limit enforcement can be disabled."""
        with app.app_context():
            tracker = TokenTracker(default_limit=100, enforce_limits=False)

            # Use more than limit
            tracker.record_usage("user-123", None, 200, 200)

            allowed, remaining = tracker.check_limit("user-123")

            # Should still be allowed when enforcement disabled
            assert allowed is True

    def test_get_usage_stats(self, app):
        """Test getting usage statistics."""
        with app.app_context():
            tracker = TokenTracker(default_limit=10000)

            tracker.record_usage("user-123", None, 100, 200)
            tracker.record_usage("user-123", None, 50, 100)

            stats = tracker.get_usage("user-123")

            assert stats["current_period"]["total_tokens"] == 450
            assert stats["current_period"]["input_tokens"] == 150
            assert stats["current_period"]["output_tokens"] == 300
            assert stats["current_period"]["request_count"] == 2
            assert stats["current_period"]["limit"] == 10000
            assert stats["current_period"]["remaining"] == 9550
            assert stats["current_period"]["percentage_used"] == 4.5

    def test_get_usage_empty(self, app):
        """Test getting usage for user with no history."""
        with app.app_context():
            tracker = TokenTracker()

            stats = tracker.get_usage("new-user")

            assert stats["current_period"]["total_tokens"] == 0
            assert stats["current_period"]["remaining"] == 100000

    def test_set_custom_limit(self, app):
        """Test setting a custom limit for a user."""
        with app.app_context():
            tracker = TokenTracker(default_limit=100000)

            tracker.set_limit("user-123", None, 50000)

            stats = tracker.get_usage("user-123")
            assert stats["current_period"]["limit"] == 50000

    def test_usage_separated_by_period(self, app):
        """Test that usage is tracked per month."""
        with app.app_context():
            tracker = TokenTracker()

            # Record usage
            tracker.record_usage("user-123", None, 100, 100)

            # Check current period
            now = utcnow()
            usage = TokenUsage.query.filter_by(
                user_id="user-123",
                period_year=now.year,
                period_month=now.month,
            ).first()

            assert usage is not None
            assert usage.total_tokens == 200

    def test_team_usage_tracking(self, app):
        """Test usage tracking for teams."""
        with app.app_context():
            tracker = TokenTracker()

            tracker.record_usage(None, "team-abc", 100, 200)

            stats = tracker.get_usage(None, "team-abc")

            assert stats["current_period"]["total_tokens"] == 300

    def test_no_user_or_team_skips_tracking(self, app):
        """Test that recording without user/team is skipped."""
        with app.app_context():
            tracker = TokenTracker()

            result = tracker.record_usage(None, None, 100, 200)

            assert result is None
            assert TokenUsage.query.count() == 0


class TestTokenLimitExceededError:
    """Tests for TokenLimitExceededError."""

    def test_error_has_remaining(self):
        """Test that error includes remaining tokens."""
        error = TokenLimitExceededError("Limit exceeded", remaining=500)

        assert error.remaining == 500
        assert "Limit exceeded" in str(error)

    def test_error_default_remaining(self):
        """Test error with default remaining value."""
        error = TokenLimitExceededError("Limit exceeded")

        assert error.remaining == 0


class TestUsageEndpoints:
    """Tests for usage API endpoints."""

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

    def test_get_usage_endpoint(self, client):
        """Test GET /api/usage endpoint."""
        response = client.get("/api/usage")

        assert response.status_code == 200
        data = response.get_json()
        assert "current_period" in data

    def test_check_usage_endpoint(self, client):
        """Test GET /api/usage/check endpoint."""
        response = client.get("/api/usage/check")

        assert response.status_code == 200
        data = response.get_json()
        assert "allowed" in data
        assert "remaining" in data
        assert "limit" in data

    def test_usage_response_format(self, client):
        """Test usage response format."""
        response = client.get("/api/usage")

        data = response.get_json()
        period = data["current_period"]

        assert "year" in period
        assert "month" in period
        assert "total_tokens" in period
        assert "limit" in period
        assert "remaining" in period
        assert "percentage_used" in period


class TestTokenTrackerInit:
    """Tests for token tracker initialization."""

    def test_init_token_tracker(self):
        """Test token tracker initialization."""
        app = create_app(TestingConfig)

        with app.app_context():
            tracker = init_token_tracker(app)

            assert tracker is not None
            assert isinstance(tracker, TokenTracker)

    def test_get_token_tracker_singleton(self):
        """Test that get_token_tracker returns singleton."""
        app = create_app(TestingConfig)

        with app.app_context():
            init_token_tracker(app)

            tracker1 = get_token_tracker()
            tracker2 = get_token_tracker()

            assert tracker1 is tracker2
