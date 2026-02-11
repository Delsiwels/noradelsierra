"""
Token Usage Tracker

Tracks and enforces token usage limits per user/team.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from flask import current_app

from webapp.models import TokenUsage, db
from webapp.time_utils import utcnow

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)


class TokenLimitExceededError(Exception):
    """Raised when token limit is exceeded."""

    def __init__(self, message: str, remaining: int = 0):
        super().__init__(message)
        self.remaining = remaining


class TokenTracker:
    """
    Tracks token usage and enforces monthly limits.

    Usage:
        tracker = TokenTracker()

        # Check if request is allowed
        allowed, remaining = tracker.check_limit(user_id)

        # Record usage after request
        tracker.record_usage(user_id, team_id, input_tokens=100, output_tokens=200)

        # Get usage stats
        stats = tracker.get_usage(user_id)
    """

    def __init__(self, default_limit: int | None = None, enforce_limits: bool = True):
        """
        Initialize the token tracker.

        Args:
            default_limit: Default monthly token limit (uses config if not provided)
            enforce_limits: Whether to enforce token limits
        """
        self._default_limit = default_limit
        self._enforce_limits = enforce_limits

    @property
    def default_limit(self) -> int:
        """Get the default monthly token limit."""
        if self._default_limit is not None:
            return self._default_limit
        try:
            return int(current_app.config.get("DEFAULT_MONTHLY_TOKEN_LIMIT", 100000))
        except RuntimeError:
            return 100000

    @property
    def enforce_limits(self) -> bool:
        """Check if limit enforcement is enabled."""
        # If explicitly set in constructor, use that value
        if not self._enforce_limits:
            return False
        try:
            return bool(current_app.config.get("TOKEN_LIMIT_ENFORCEMENT", True))
        except RuntimeError:
            return self._enforce_limits

    def _get_current_period(self) -> tuple[int, int]:
        """Get current year and month."""
        now = utcnow()
        return now.year, now.month

    def _get_or_create_usage(
        self,
        user_id: str | None,
        team_id: str | None,
    ) -> TokenUsage:
        """Get or create token usage record for current period."""
        year, month = self._get_current_period()

        usage = TokenUsage.query.filter_by(
            user_id=user_id,
            team_id=team_id,
            period_year=year,
            period_month=month,
        ).first()

        if usage is None:
            usage = TokenUsage(
                user_id=user_id,
                team_id=team_id,
                period_year=year,
                period_month=month,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                request_count=0,
            )
            db.session.add(usage)
            db.session.flush()  # Get ID without committing

        return usage  # type: ignore[no-any-return]

    def check_limit(
        self,
        user_id: str | None,
        team_id: str | None = None,
    ) -> tuple[bool, int]:
        """
        Check if a request is allowed based on token limits.

        Args:
            user_id: User ID to check
            team_id: Optional team ID for team-based limits

        Returns:
            Tuple of (allowed, remaining_tokens)
        """
        if not self.enforce_limits:
            return True, self.default_limit

        if user_id is None and team_id is None:
            return True, self.default_limit

        usage = self._get_or_create_usage(user_id, team_id)

        # Determine limit (custom or default)
        limit = (
            usage.monthly_limit
            if usage.monthly_limit is not None
            else self.default_limit
        )
        remaining = max(0, limit - (usage.total_tokens or 0))

        allowed = remaining > 0

        logger.debug(
            f"Token limit check: user={user_id}, team={team_id}, "
            f"used={usage.total_tokens}, limit={limit}, remaining={remaining}"
        )

        return allowed, remaining

    def record_usage(
        self,
        user_id: str | None,
        team_id: str | None,
        input_tokens: int,
        output_tokens: int,
    ) -> TokenUsage | None:
        """
        Record token usage for a request.

        Args:
            user_id: User ID
            team_id: Optional team ID
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens generated

        Returns:
            Updated TokenUsage record, or None if no user/team
        """
        if user_id is None and team_id is None:
            logger.warning("Cannot record usage without user_id or team_id")
            return None

        usage = self._get_or_create_usage(user_id, team_id)

        # Atomically increment counters
        usage.input_tokens = (usage.input_tokens or 0) + input_tokens
        usage.output_tokens = (usage.output_tokens or 0) + output_tokens
        usage.total_tokens = (usage.total_tokens or 0) + input_tokens + output_tokens
        usage.request_count = (usage.request_count or 0) + 1

        db.session.commit()

        logger.debug(
            f"Recorded usage: user={user_id}, team={team_id}, "
            f"input={input_tokens}, output={output_tokens}, "
            f"total_now={usage.total_tokens}"
        )

        return usage

    def get_usage(
        self,
        user_id: str | None,
        team_id: str | None = None,
    ) -> dict:
        """
        Get current period usage statistics.

        Args:
            user_id: User ID
            team_id: Optional team ID

        Returns:
            Dictionary with usage statistics
        """
        year, month = self._get_current_period()

        usage = TokenUsage.query.filter_by(
            user_id=user_id,
            team_id=team_id,
            period_year=year,
            period_month=month,
        ).first()

        limit = self.default_limit
        total_tokens = 0
        input_tokens = 0
        output_tokens = 0
        request_count = 0

        if usage:
            if usage.monthly_limit is not None:
                limit = usage.monthly_limit
            total_tokens = usage.total_tokens or 0
            input_tokens = usage.input_tokens or 0
            output_tokens = usage.output_tokens or 0
            request_count = usage.request_count or 0

        remaining = max(0, limit - total_tokens)
        percentage_used = (total_tokens / limit * 100) if limit > 0 else 0

        return {
            "current_period": {
                "year": year,
                "month": month,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "request_count": request_count,
                "limit": limit,
                "remaining": remaining,
                "percentage_used": round(percentage_used, 1),
            },
            "enforcement_enabled": self.enforce_limits,
        }

    def set_limit(
        self,
        user_id: str | None,
        team_id: str | None,
        monthly_limit: int | None,
    ) -> TokenUsage:
        """
        Set a custom monthly limit for a user or team.

        Args:
            user_id: User ID
            team_id: Team ID
            monthly_limit: Custom limit (None to use default)

        Returns:
            Updated TokenUsage record
        """
        usage = self._get_or_create_usage(user_id, team_id)
        usage.monthly_limit = monthly_limit
        db.session.commit()

        logger.info(
            f"Set custom limit: user={user_id}, team={team_id}, limit={monthly_limit}"
        )

        return usage


# Module-level singleton
_token_tracker: TokenTracker | None = None


def get_token_tracker() -> TokenTracker:
    """Get or create the default token tracker singleton."""
    global _token_tracker
    if _token_tracker is None:
        _token_tracker = TokenTracker()
    return _token_tracker


def init_token_tracker(app: Flask) -> TokenTracker:
    """
    Initialize the token tracker from Flask app config.

    Args:
        app: Flask application instance

    Returns:
        Configured TokenTracker instance
    """
    global _token_tracker

    default_limit = app.config.get("DEFAULT_MONTHLY_TOKEN_LIMIT", 100000)
    enforce_limits = app.config.get("TOKEN_LIMIT_ENFORCEMENT", True)

    _token_tracker = TokenTracker(
        default_limit=default_limit,
        enforce_limits=enforce_limits,
    )

    logger.info(
        f"Token tracker initialized: limit={default_limit}, enforce={enforce_limits}"
    )

    return _token_tracker
