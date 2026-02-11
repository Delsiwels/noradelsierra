"""
Skill Analytics Service

Tracks and reports skill usage statistics.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func

from webapp.models import SkillUsage, db
from webapp.time_utils import utcnow

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)


class SkillAnalyticsService:
    """
    Service for tracking and analyzing skill usage.

    Usage:
        service = SkillAnalyticsService()

        # Log skill usage
        service.log_usage('tax_agent', 'public', user_id, ...)

        # Get top skills
        top_skills = service.get_top_skills(period_days=30, limit=10)

        # Get user stats
        stats = service.get_user_stats(user_id)
    """

    def log_usage(
        self,
        skill_name: str,
        skill_source: str,
        user_id: str | None = None,
        team_id: str | None = None,
        trigger: str | None = None,
        confidence: float | None = None,
        conversation_id: str | None = None,
    ) -> SkillUsage:
        """
        Log a skill usage event.

        Args:
            skill_name: Name of the skill used
            skill_source: Source type ('public', 'private', 'shared')
            user_id: User who triggered the skill
            team_id: Team context (optional)
            trigger: Trigger phrase that matched
            confidence: Match confidence score
            conversation_id: Associated conversation ID

        Returns:
            Created SkillUsage record
        """
        usage = SkillUsage(
            skill_name=skill_name,
            skill_source=skill_source,
            user_id=user_id,
            team_id=team_id,
            trigger=trigger,
            confidence=confidence,
            conversation_id=conversation_id,
        )

        db.session.add(usage)
        db.session.commit()

        logger.debug(
            f"Logged skill usage: {skill_name} ({skill_source}) by user {user_id}"
        )

        return usage

    def get_top_skills(
        self,
        period_days: int = 30,
        limit: int = 10,
        user_id: str | None = None,
        team_id: str | None = None,
    ) -> list[dict]:
        """
        Get the most used skills in the specified period.

        Args:
            period_days: Number of days to look back
            limit: Maximum number of skills to return
            user_id: Filter by user (optional)
            team_id: Filter by team (optional)

        Returns:
            List of dicts with skill_name, skill_source, usage_count, avg_confidence
        """
        since = utcnow() - timedelta(days=period_days)

        query = db.session.query(
            SkillUsage.skill_name,
            SkillUsage.skill_source,
            func.count(SkillUsage.id).label("usage_count"),
            func.avg(SkillUsage.confidence).label("avg_confidence"),
        ).filter(SkillUsage.created_at >= since)

        if user_id:
            query = query.filter(SkillUsage.user_id == user_id)
        if team_id:
            query = query.filter(SkillUsage.team_id == team_id)

        query = query.group_by(SkillUsage.skill_name, SkillUsage.skill_source)
        query = query.order_by(func.count(SkillUsage.id).desc())
        query = query.limit(limit)

        results = query.all()

        return [
            {
                "skill_name": r.skill_name,
                "skill_source": r.skill_source,
                "usage_count": r.usage_count,
                "avg_confidence": round(r.avg_confidence or 0, 3),
            }
            for r in results
        ]

    def get_user_stats(self, user_id: str) -> dict:
        """
        Get skill usage statistics for a specific user.

        Args:
            user_id: User ID

        Returns:
            Dict with total_usages, skills_used, top_skills, recent_activity
        """
        # Total usage count
        total_usages = SkillUsage.query.filter_by(user_id=user_id).count()

        # Distinct skills used
        skills_used = (
            db.session.query(func.count(func.distinct(SkillUsage.skill_name)))
            .filter(SkillUsage.user_id == user_id)
            .scalar()
            or 0
        )

        # Top skills for this user
        top_skills = self.get_top_skills(period_days=90, limit=5, user_id=user_id)

        # Recent activity (last 7 days)
        week_ago = utcnow() - timedelta(days=7)
        recent_count = SkillUsage.query.filter(
            SkillUsage.user_id == user_id,
            SkillUsage.created_at >= week_ago,
        ).count()

        # Usage by source
        by_source = {}
        source_query = (
            db.session.query(
                SkillUsage.skill_source,
                func.count(SkillUsage.id).label("count"),
            )
            .filter(SkillUsage.user_id == user_id)
            .group_by(SkillUsage.skill_source)
        )

        for row in source_query.all():
            by_source[row.skill_source] = row.count

        return {
            "user_id": user_id,
            "total_usages": total_usages,
            "skills_used": skills_used,
            "top_skills": top_skills,
            "recent_activity": {
                "last_7_days": recent_count,
            },
            "by_source": by_source,
        }

    def get_skill_stats(self, skill_name: str) -> dict:
        """
        Get usage statistics for a specific skill.

        Args:
            skill_name: Name of the skill

        Returns:
            Dict with total_usages, unique_users, avg_confidence, usage_trend
        """
        # Total usage count
        total_usages = SkillUsage.query.filter_by(skill_name=skill_name).count()

        # Unique users
        unique_users = (
            db.session.query(func.count(func.distinct(SkillUsage.user_id)))
            .filter(SkillUsage.skill_name == skill_name)
            .scalar()
            or 0
        )

        # Average confidence
        avg_confidence = (
            db.session.query(func.avg(SkillUsage.confidence))
            .filter(SkillUsage.skill_name == skill_name)
            .scalar()
            or 0
        )

        # Usage trend (daily for last 30 days)
        thirty_days_ago = utcnow() - timedelta(days=30)
        daily_usage = (
            db.session.query(
                func.date(SkillUsage.created_at).label("date"),
                func.count(SkillUsage.id).label("count"),
            )
            .filter(
                SkillUsage.skill_name == skill_name,
                SkillUsage.created_at >= thirty_days_ago,
            )
            .group_by(func.date(SkillUsage.created_at))
            .all()
        )

        trend = [{"date": str(d.date), "count": d.count} for d in daily_usage]

        # Top triggers
        top_triggers = (
            db.session.query(
                SkillUsage.trigger,
                func.count(SkillUsage.id).label("count"),
            )
            .filter(
                SkillUsage.skill_name == skill_name,
                SkillUsage.trigger.isnot(None),
            )
            .group_by(SkillUsage.trigger)
            .order_by(func.count(SkillUsage.id).desc())
            .limit(5)
            .all()
        )

        triggers = [{"trigger": t.trigger, "count": t.count} for t in top_triggers]

        return {
            "skill_name": skill_name,
            "total_usages": total_usages,
            "unique_users": unique_users,
            "avg_confidence": round(avg_confidence, 3),
            "usage_trend": trend,
            "top_triggers": triggers,
        }

    def get_summary(self, period_days: int = 30) -> dict:
        """
        Get overall skill usage summary.

        Args:
            period_days: Number of days to look back

        Returns:
            Dict with total_usages, active_skills, active_users, by_source
        """
        since = utcnow() - timedelta(days=period_days)

        # Total usages in period
        total_usages = SkillUsage.query.filter(SkillUsage.created_at >= since).count()

        # Active skills
        active_skills = (
            db.session.query(func.count(func.distinct(SkillUsage.skill_name)))
            .filter(SkillUsage.created_at >= since)
            .scalar()
            or 0
        )

        # Active users
        active_users = (
            db.session.query(func.count(func.distinct(SkillUsage.user_id)))
            .filter(SkillUsage.created_at >= since)
            .scalar()
            or 0
        )

        # Usage by source
        by_source = {}
        source_query = (
            db.session.query(
                SkillUsage.skill_source,
                func.count(SkillUsage.id).label("count"),
            )
            .filter(SkillUsage.created_at >= since)
            .group_by(SkillUsage.skill_source)
        )

        for row in source_query.all():
            by_source[row.skill_source] = row.count

        return {
            "period_days": period_days,
            "total_usages": total_usages,
            "active_skills": active_skills,
            "active_users": active_users,
            "by_source": by_source,
        }


# Module-level singleton
_analytics_service: SkillAnalyticsService | None = None


def get_analytics_service() -> SkillAnalyticsService:
    """Get or create the default analytics service singleton."""
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = SkillAnalyticsService()
    return _analytics_service


def init_analytics_service(app: Flask) -> SkillAnalyticsService:
    """
    Initialize the analytics service from Flask app config.

    Args:
        app: Flask application instance

    Returns:
        Configured SkillAnalyticsService instance
    """
    global _analytics_service

    _analytics_service = SkillAnalyticsService()
    logger.info("Skill analytics service initialized")

    return _analytics_service
