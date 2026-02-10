"""Operational maintenance tasks reused by scheduler and admin controls."""

from __future__ import annotations

import logging
from datetime import datetime

from flask import Flask

from webapp.models import Conversation, db
from webapp.services.runtime_health import runtime_health
from webapp.services.runtime_health_persistence import persist_runtime_health_snapshot

logger = logging.getLogger(__name__)


def cleanup_expired_conversations(app: Flask) -> int:
    """Delete expired conversations and return deleted row count."""
    with app.app_context():
        now = datetime.utcnow()
        expired = Conversation.query.filter(Conversation.expires_at <= now).all()
        count = len(expired)

        for conversation in expired:
            db.session.delete(conversation)

        if count > 0:
            db.session.commit()
            logger.info("Cleaned up %s expired conversations", count)

        return count


def snapshot_runtime_health(app: Flask) -> str | None:
    """Persist one runtime health snapshot and return the snapshot ID."""
    report = runtime_health.build_report(app)
    return persist_runtime_health_snapshot(app, report)
