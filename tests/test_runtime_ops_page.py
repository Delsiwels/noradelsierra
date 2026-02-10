"""Tests for runtime operations dashboard page."""


def _register(client, email: str = "owner@example.com"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": "securepass123", "name": "Owner User"},
    )


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

    with app.app_context():
        from flask_bcrypt import generate_password_hash

        from webapp.models import User, db

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

    client.post("/api/auth/logout")
    login = client.post(
        "/api/auth/login",
        json={"email": "member@example.com", "password": "securepass123"},
    )
    assert login.status_code == 200

    response = client.get("/ops/runtime-health")
    assert response.status_code == 403
    assert b"Access Denied" in response.data
