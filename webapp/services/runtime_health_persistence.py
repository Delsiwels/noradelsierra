"""Persistence helpers for runtime health history."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from flask import Flask

from webapp.models import RuntimeHealthSnapshot, db
from webapp.services.operational_alerts import send_operational_alert

logger = logging.getLogger(__name__)


def persist_runtime_health_snapshot(app: Flask, report: dict) -> str | None:
    """Persist a runtime health report and trim historical rows."""
    if not app.config.get("RUNTIME_HEALTH_SNAPSHOT_ENABLED", True):
        return None

    with app.app_context():
        snapshot = RuntimeHealthSnapshot(
            status=report.get("status", "healthy"),
            degraded_reasons=report.get("degraded_reasons", []),
            scheduler=report.get("scheduler", {}),
            jobs=report.get("jobs", {}),
            queue=report.get("queue", {}),
            startup_config_audit=report.get("startup_config_audit", {}),
        )
        db.session.add(snapshot)
        db.session.commit()

        _trim_runtime_health_snapshots(app)

        if snapshot.status != "healthy":
            send_operational_alert(
                app,
                event_type="runtime_health_degraded",
                severity="high",
                message="Runtime health status is degraded.",
                details={
                    "snapshot_id": snapshot.id,
                    "degraded_reasons": snapshot.degraded_reasons or [],
                },
                dedupe_key="runtime_health_degraded",
            )

        return str(snapshot.id)


def list_runtime_health_snapshots(limit: int = 25) -> list[dict]:
    """Return latest persisted runtime health snapshots."""
    clamped_limit = max(1, min(limit, 200))
    snapshots = (
        RuntimeHealthSnapshot.query.order_by(RuntimeHealthSnapshot.created_at.desc())
        .limit(clamped_limit)
        .all()
    )
    return [snapshot.to_dict() for snapshot in snapshots]


def _trim_runtime_health_snapshots(app: Flask) -> None:
    retention_days = int(app.config.get("RUNTIME_HEALTH_SNAPSHOT_RETENTION_DAYS", 30))
    max_rows = int(app.config.get("RUNTIME_HEALTH_SNAPSHOT_MAX_ROWS", 2000))

    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=retention_days)
    RuntimeHealthSnapshot.query.filter(
        RuntimeHealthSnapshot.created_at < cutoff
    ).delete(synchronize_session=False)
    db.session.commit()

    ids_to_keep = [
        row.id
        for row in RuntimeHealthSnapshot.query.order_by(
            RuntimeHealthSnapshot.created_at.desc()
        )
        .limit(max_rows)
        .all()
    ]
    if not ids_to_keep:
        return

    deleted = RuntimeHealthSnapshot.query.filter(
        ~RuntimeHealthSnapshot.id.in_(ids_to_keep)
    ).delete(synchronize_session=False)
    if deleted:
        db.session.commit()
        logger.info("Trimmed %s runtime health snapshots", deleted)
