"""Tests for runtime health reporting."""

from flask import Flask

from webapp.services.runtime_health import RuntimeHealthRegistry


def test_scheduler_and_job_state_are_reported():
    registry = RuntimeHealthRegistry()
    registry.register_job("cleanup_expired_conversations", "0 * * * *")
    registry.mark_job_success("cleanup_expired_conversations")
    registry.set_scheduler_state(
        enabled=True,
        started=True,
        warnings=[],
        registered_jobs=["cleanup_expired_conversations"],
        skipped_jobs=[],
    )

    report = registry.build_report()

    assert report["scheduler"]["enabled"] is True
    assert report["scheduler"]["started"] is True
    assert "cleanup_expired_conversations" in report["jobs"]
    assert (
        report["jobs"]["cleanup_expired_conversations"]["last_success_utc"] is not None
    )


def test_queue_summary_uses_app_extensions():
    app = Flask(__name__)
    app.extensions["task_queue"] = [1, 2, 3]
    app.extensions["dead_letter_queue"] = []

    registry = RuntimeHealthRegistry()
    report = registry.build_report(app)

    assert report["queue"]["available"] is True
    assert report["queue"]["task_queue_size"] == 3
    assert report["queue"]["dead_letter_queue_size"] == 0


def test_optional_blueprints_are_reported_from_app_extensions():
    app = Flask(__name__)
    app.extensions["optional_blueprints"] = {
        "webapp.blueprints.ask_fin.ask_fin_bp": True,
        "webapp.blueprints.sample.sample_bp": False,
    }

    registry = RuntimeHealthRegistry()
    report = registry.build_report(app)

    assert report["optional_blueprints"] == {
        "webapp.blueprints.ask_fin.ask_fin_bp": True,
        "webapp.blueprints.sample.sample_bp": False,
    }
