"""Tests for PDF export service and blueprint."""

import pytest


@pytest.fixture
def app():
    """Create test Flask app."""
    from webapp.app import create_app
    from webapp.config import TestingConfig

    app = create_app(TestingConfig)
    app.config["TESTING"] = True

    with app.app_context():
        from webapp.models import db

        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    from webapp.models import db as _db

    return _db


def _create_test_conversation(db):
    """Create a test conversation with messages."""
    from webapp.models import Conversation, Message

    conv = Conversation(user_id="test-user-123", title="Test Conversation")
    db.session.add(conv)
    db.session.flush()

    msg1 = Message(
        conversation_id=conv.id,
        role="user",
        content="What is GST?",
    )
    msg2 = Message(
        conversation_id=conv.id,
        role="assistant",
        content="GST (Goods and Services Tax) is a 10% tax on most goods and services in Australia.",
        model="claude-sonnet",
        skills_used=["tax_agent"],
        input_tokens=100,
        output_tokens=50,
    )
    db.session.add_all([msg1, msg2])
    db.session.commit()
    return conv


class TestPdfExportService:
    """Tests for the PDF export service."""

    def test_export_conversation(self, app, db):
        """Test exporting a single conversation."""
        conv = _create_test_conversation(db)

        from webapp.services.pdf_export import export_conversation

        pdf_bytes = export_conversation(conv.id)
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 0

    def test_export_conversation_with_business_name(self, app, db):
        """Test export with business name in header."""
        conv = _create_test_conversation(db)

        from webapp.services.pdf_export import export_conversation

        pdf_bytes = export_conversation(conv.id, business_name="Test Business Pty Ltd")
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 0

    def test_export_nonexistent_conversation(self, app, db):
        """Test exporting a nonexistent conversation raises ValueError."""
        from webapp.services.pdf_export import export_conversation

        with pytest.raises(ValueError, match="not found"):
            export_conversation("nonexistent-id")

    def test_export_compliance_summary(self, app, db):
        """Test compliance summary export."""
        from webapp.models import Team, User

        team = Team(name="Test Team", owner_id="owner-1")
        db.session.add(team)
        db.session.flush()

        user = User(
            email="user@test.com",
            password_hash="hash",
            name="Test",
            role="owner",
            team_id=team.id,
        )
        db.session.add(user)
        db.session.flush()

        from webapp.models import Conversation, Message

        conv = Conversation(user_id=user.id, title="BAS Review")
        db.session.add(conv)
        db.session.flush()

        msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content="BAS review content",
            input_tokens=200,
            output_tokens=100,
        )
        db.session.add(msg)
        db.session.commit()

        from webapp.services.pdf_export import export_compliance_summary

        pdf_bytes = export_compliance_summary(team.id)
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 0

    def test_export_bulk_conversations(self, app, db):
        """Test bulk conversation export."""
        conv1 = _create_test_conversation(db)

        from webapp.models import Conversation, Message

        conv2 = Conversation(user_id="test-user-123", title="Second Conversation")
        db.session.add(conv2)
        db.session.flush()
        msg = Message(conversation_id=conv2.id, role="user", content="Hello")
        db.session.add(msg)
        db.session.commit()

        from webapp.services.pdf_export import export_bulk_conversations

        pdf_bytes = export_bulk_conversations([conv1.id, conv2.id])
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 0


class TestExportBlueprint:
    """Tests for the export API endpoints."""

    def test_export_conversation_pdf_endpoint(self, client, db):
        """Test the conversation PDF download endpoint."""
        conv = _create_test_conversation(db)

        # Register and login a user
        client.post(
            "/api/auth/register",
            json={"email": "test@test.com", "password": "password123", "name": "Test"},
        )

        # Update conversation user_id to match the logged in user
        from webapp.models import User

        user = User.query.filter_by(email="test@test.com").first()
        conv.user_id = user.id
        db.session.commit()

        res = client.get(f"/api/export/conversation/{conv.id}/pdf")
        assert res.status_code == 200
        assert res.content_type == "application/pdf"

    def test_export_conversation_pdf_not_found(self, client):
        """Test exporting nonexistent conversation."""
        client.post(
            "/api/auth/register",
            json={"email": "test@test.com", "password": "password123", "name": "Test"},
        )
        res = client.get("/api/export/conversation/nonexistent/pdf")
        assert res.status_code == 404

    def test_export_compliance_pdf_endpoint(self, client, db):
        """Test compliance summary PDF endpoint."""
        client.post(
            "/api/auth/register",
            json={"email": "test@test.com", "password": "password123", "name": "Test"},
        )
        res = client.get("/api/export/compliance/pdf")
        assert res.status_code == 200

    def test_export_bulk_pdf_endpoint(self, client, db):
        """Test bulk export PDF endpoint."""
        conv = _create_test_conversation(db)

        client.post(
            "/api/auth/register",
            json={"email": "test@test.com", "password": "password123", "name": "Test"},
        )

        from webapp.models import User

        user = User.query.filter_by(email="test@test.com").first()
        conv.user_id = user.id
        db.session.commit()

        res = client.post(
            "/api/export/bulk/pdf",
            json={"conversation_ids": [conv.id]},
        )
        assert res.status_code == 200

    def test_export_bulk_no_ids(self, client):
        """Test bulk export with no conversation IDs."""
        client.post(
            "/api/auth/register",
            json={"email": "test@test.com", "password": "password123", "name": "Test"},
        )
        res = client.post("/api/export/bulk/pdf", json={"conversation_ids": []})
        assert res.status_code == 400
