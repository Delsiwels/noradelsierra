"""Tests for conversation persistence."""

from datetime import timedelta

import pytest

from webapp.app import cleanup_expired_conversations, create_app
from webapp.config import TestingConfig
from webapp.models import Conversation, Message, db
from webapp.time_utils import utcnow


class TestConversationModel:
    """Tests for Conversation model."""

    @pytest.fixture
    def app(self):
        """Create test app."""
        app = create_app(TestingConfig)
        with app.app_context():
            db.create_all()
        yield app
        with app.app_context():
            db.drop_all()

    def test_create_conversation(self, app):
        """Test creating a conversation."""
        with app.app_context():
            conv = Conversation(
                user_id="user-123",
                title="Test conversation",
            )
            db.session.add(conv)
            db.session.commit()

            assert conv.id is not None
            assert conv.user_id == "user-123"
            assert conv.title == "Test conversation"
            assert conv.created_at is not None
            assert conv.expires_at is not None

    def test_conversation_default_expiry(self, app):
        """Test that conversations have 30-day default expiry."""
        with app.app_context():
            conv = Conversation(user_id="user-123")
            db.session.add(conv)
            db.session.commit()

            # Should expire in ~30 days
            now = utcnow()
            delta = conv.expires_at - now
            assert 29 <= delta.days <= 30

    def test_conversation_to_dict(self, app):
        """Test conversation serialization."""
        with app.app_context():
            conv = Conversation(
                user_id="user-123",
                title="Test",
            )
            db.session.add(conv)
            db.session.commit()

            data = conv.to_dict()

            assert data["id"] == conv.id
            assert data["user_id"] == "user-123"
            assert data["title"] == "Test"
            assert "created_at" in data
            assert "expires_at" in data

    def test_conversation_to_dict_with_messages(self, app):
        """Test conversation serialization with messages."""
        with app.app_context():
            conv = Conversation(user_id="user-123")
            db.session.add(conv)
            db.session.flush()

            msg1 = Message(
                conversation_id=conv.id,
                role="user",
                content="Hello",
            )
            msg2 = Message(
                conversation_id=conv.id,
                role="assistant",
                content="Hi there!",
            )
            db.session.add_all([msg1, msg2])
            db.session.commit()

            data = conv.to_dict(include_messages=True)

            assert "messages" in data
            assert len(data["messages"]) == 2

    def test_conversation_messages_relationship(self, app):
        """Test conversation-message relationship."""
        with app.app_context():
            conv = Conversation(user_id="user-123")
            db.session.add(conv)
            db.session.flush()

            msg = Message(
                conversation_id=conv.id,
                role="user",
                content="Test message",
            )
            db.session.add(msg)
            db.session.commit()

            assert conv.messages.count() == 1
            assert msg.conversation == conv


class TestMessageModel:
    """Tests for Message model."""

    @pytest.fixture
    def app(self):
        """Create test app."""
        app = create_app(TestingConfig)
        with app.app_context():
            db.create_all()
        yield app
        with app.app_context():
            db.drop_all()

    def test_create_message(self, app):
        """Test creating a message."""
        with app.app_context():
            conv = Conversation(user_id="user-123")
            db.session.add(conv)
            db.session.flush()

            msg = Message(
                conversation_id=conv.id,
                role="user",
                content="Hello",
            )
            db.session.add(msg)
            db.session.commit()

            assert msg.id is not None
            assert msg.role == "user"
            assert msg.content == "Hello"

    def test_message_with_metadata(self, app):
        """Test message with full metadata."""
        with app.app_context():
            conv = Conversation(user_id="user-123")
            db.session.add(conv)
            db.session.flush()

            msg = Message(
                conversation_id=conv.id,
                role="assistant",
                content="Response",
                model="gpt-4",
                skills_used=["tax_agent", "accountant"],
                input_tokens=100,
                output_tokens=200,
            )
            db.session.add(msg)
            db.session.commit()

            assert msg.model == "gpt-4"
            assert msg.skills_used == ["tax_agent", "accountant"]
            assert msg.input_tokens == 100
            assert msg.output_tokens == 200

    def test_message_to_dict(self, app):
        """Test message serialization."""
        with app.app_context():
            conv = Conversation(user_id="user-123")
            db.session.add(conv)
            db.session.flush()

            msg = Message(
                conversation_id=conv.id,
                role="assistant",
                content="Hello!",
                skills_used=["test_skill"],
            )
            db.session.add(msg)
            db.session.commit()

            data = msg.to_dict()

            assert data["role"] == "assistant"
            assert data["content"] == "Hello!"
            assert data["skills_used"] == ["test_skill"]

    def test_cascade_delete(self, app):
        """Test that deleting conversation deletes messages."""
        with app.app_context():
            conv = Conversation(user_id="user-123")
            db.session.add(conv)
            db.session.flush()

            msg = Message(
                conversation_id=conv.id,
                role="user",
                content="Test",
            )
            db.session.add(msg)
            db.session.commit()

            msg_id = msg.id

            db.session.delete(conv)
            db.session.commit()

            assert Message.query.get(msg_id) is None


class TestConversationEndpoints:
    """Tests for conversation API endpoints."""

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

    def test_list_conversations_empty(self, client):
        """Test listing conversations when empty."""
        response = client.get("/api/conversations")

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["conversations"] == []
        assert data["total"] == 0

    def test_get_conversation_not_found(self, client):
        """Test getting non-existent conversation."""
        response = client.get("/api/conversations/nonexistent")

        assert response.status_code == 404

    def test_delete_conversation_not_found(self, client):
        """Test deleting non-existent conversation."""
        response = client.delete("/api/conversations/nonexistent")

        assert response.status_code == 404

    def test_get_conversation_with_messages(self, client, app):
        """Test getting conversation with messages."""
        with app.app_context():
            conv = Conversation(user_id="test-user")
            db.session.add(conv)
            db.session.flush()

            msg = Message(
                conversation_id=conv.id,
                role="user",
                content="Test message",
            )
            db.session.add(msg)
            db.session.commit()
            conv_id = conv.id

        response = client.get(f"/api/conversations/{conv_id}")

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "messages" in data["conversation"]

    def test_delete_conversation_success(self, client, app):
        """Test successful conversation deletion."""
        with app.app_context():
            conv = Conversation(user_id="test-user")
            db.session.add(conv)
            db.session.commit()
            conv_id = conv.id

        response = client.delete(f"/api/conversations/{conv_id}")

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        # Verify deleted
        response = client.get(f"/api/conversations/{conv_id}")
        assert response.status_code == 404


class TestConversationCleanup:
    """Tests for conversation cleanup functionality."""

    @pytest.fixture
    def app(self):
        """Create test app."""
        app = create_app(TestingConfig)
        with app.app_context():
            db.create_all()
        yield app
        with app.app_context():
            db.drop_all()

    def test_cleanup_expired_conversations(self, app):
        """Test that expired conversations are cleaned up."""
        with app.app_context():
            # Create expired conversation
            expired = Conversation(user_id="user-1")
            expired.expires_at = utcnow() - timedelta(days=1)
            db.session.add(expired)

            # Create valid conversation
            valid = Conversation(user_id="user-2")
            valid.expires_at = utcnow() + timedelta(days=10)
            db.session.add(valid)

            db.session.commit()

        count = cleanup_expired_conversations(app)

        assert count == 1

        with app.app_context():
            remaining = Conversation.query.count()
            assert remaining == 1

    def test_cleanup_no_expired_conversations(self, app):
        """Test cleanup when no expired conversations."""
        with app.app_context():
            conv = Conversation(user_id="user-1")
            conv.expires_at = utcnow() + timedelta(days=30)
            db.session.add(conv)
            db.session.commit()

        count = cleanup_expired_conversations(app)

        assert count == 0

    def test_cleanup_deletes_messages_too(self, app):
        """Test that cleanup deletes associated messages."""
        with app.app_context():
            conv = Conversation(user_id="user-1")
            conv.expires_at = utcnow() - timedelta(days=1)
            db.session.add(conv)
            db.session.flush()

            msg = Message(
                conversation_id=conv.id,
                role="user",
                content="Test",
            )
            db.session.add(msg)
            db.session.commit()

        cleanup_expired_conversations(app)

        with app.app_context():
            assert Message.query.count() == 0


class TestChatPersistence:
    """Tests for chat message persistence."""

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

    def test_chat_without_persist(self, client, app):
        """Test that chat without persist doesn't save."""
        response = client.post(
            "/api/chat",
            json={"message": "Hello"},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert "conversation_id" not in data

        with app.app_context():
            assert Conversation.query.count() == 0
