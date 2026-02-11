"""Tests for runtime operations dashboard endpoints."""

from datetime import UTC, datetime, timedelta

from flask_bcrypt import generate_password_hash

from webapp.models import Conversation, RuntimeHealthSnapshot, User, db


def _register(client, email: str = "owner@example.com"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": "securepass123", "name": "Owner User"},
    )


def _create_member_user(app):
    with app.app_context():
        owner = User.query.filter_by(email="owner@example.com").first()
        assert owner is not None

        member = User(
            email="member@example.com",
            password_hash=generate_password_hash("securepass123").decode("utf-8"),
            name="Member User",
            role="member",
            team_id=owner.team_id,
            is_active=True,
        )
        db.session.add(member)
        db.session.commit()


def _login_member(client):
    client.post("/api/auth/logout")
    login = client.post(
        "/api/auth/login",
        json={"email": "member@example.com", "password": "securepass123"},
    )
    assert login.status_code == 200


def test_runtime_ops_page_requires_auth(client):
    response = client.get("/ops/runtime-health")
    assert response.status_code == 401


def test_runtime_ops_page_accessible_for_owner(client):
    _register(client)
    response = client.get("/ops/runtime-health")
    assert response.status_code == 200
    assert b"Runtime Health" in response.data


def test_runtime_ops_page_denied_for_non_admin(client, app):
    _register(client, email="owner@example.com")
    _create_member_user(app)
    _login_member(client)

    response = client.get("/ops/runtime-health")
    assert response.status_code == 403
    assert b"Access Denied" in response.data


def test_runtime_ops_snapshot_action_creates_snapshot(client, app):
    _register(client)

    with app.app_context():
        before_count = RuntimeHealthSnapshot.query.count()

    response = client.post("/ops/runtime-health/actions", data={"action": "snapshot"})
    assert response.status_code == 302
    assert "/ops/runtime-health" in response.headers["Location"]

    with app.app_context():
        after_count = RuntimeHealthSnapshot.query.count()
    assert after_count == before_count + 1


def test_runtime_ops_cleanup_action_returns_json(client, app):
    _register(client)

    with app.app_context():
        owner = User.query.filter_by(email="owner@example.com").first()
        assert owner is not None
        db.session.add(
            Conversation(
                user_id=owner.id,
                title="expired",
                expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
            )
        )
        db.session.commit()

    response = client.post("/ops/runtime-health/actions", json={"action": "cleanup"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["action"] == "cleanup_conversations"
    assert payload["deleted_count"] >= 1


def test_runtime_ops_action_denied_for_non_admin(client, app):
    _register(client, email="owner@example.com")
    _create_member_user(app)
    _login_member(client)

    response = client.post("/ops/runtime-health/actions", json={"action": "snapshot"})
    assert response.status_code == 403


def test_runtime_ops_incidents_csv_export(client, app):
    _register(client)

    with app.app_context():
        db.session.add_all(
            [
                RuntimeHealthSnapshot(
                    status="healthy",
                    degraded_reasons=[],
                    scheduler={},
                    jobs={},
                    queue={},
                    startup_config_audit={},
                ),
                RuntimeHealthSnapshot(
                    status="degraded",
                    degraded_reasons=["scheduler_not_started", "job_failed:cleanup"],
                    scheduler={},
                    jobs={},
                    queue={},
                    startup_config_audit={},
                ),
                RuntimeHealthSnapshot(
                    status="degraded",
                    degraded_reasons=["scheduler_not_started"],
                    scheduler={},
                    jobs={},
                    queue={},
                    startup_config_audit={},
                ),
            ]
        )
        db.session.commit()

    response = client.get(
        "/ops/runtime-health/incidents.csv?status=degraded&reason=scheduler_not_started&limit=120"
    )
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    body = response.data.decode("utf-8")
    assert "snapshot_id,timestamp_utc,status,reason" in body
    assert body.count("scheduler_not_started") >= 2
    assert "healthy" not in body


def test_runtime_ops_incidents_csv_denied_for_non_admin(client, app):
    _register(client, email="owner@example.com")
    _create_member_user(app)
    _login_member(client)

    response = client.get("/ops/runtime-health/incidents.csv")
    assert response.status_code == 403
