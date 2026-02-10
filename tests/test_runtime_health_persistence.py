"""Tests for runtime health snapshot persistence."""

from webapp.services.runtime_health import runtime_health
from webapp.services.runtime_health_persistence import (
    list_runtime_health_snapshots,
    persist_runtime_health_snapshot,
)


def test_persist_and_list_runtime_health_snapshot(app):
    with app.app_context():
        report = runtime_health.build_report(app)
        snapshot_id = persist_runtime_health_snapshot(app, report)
        assert snapshot_id is not None

        snapshots = list_runtime_health_snapshots(limit=5)
        assert snapshots
        assert any(item["id"] == snapshot_id for item in snapshots)
