"""
Tests for Chat Blueprint

Tests cover:
- POST /api/chat endpoint
- GET /api/chat/skills endpoint
- Input validation
- Error handling
- Authentication requirements
"""

import pytest
from unittest.mock import MagicMock, patch


class TestChatEndpoint:
    """Tests for POST /api/chat endpoint."""

    @pytest.fixture
    def app(self):
        """Create test Flask app."""
        from webapp.app import create_app
        from webapp.config import TestingConfig

        app = create_app(TestingConfig)
        app.config["TESTING"] = True
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        with app.test_client() as client:
            with app.app_context():
                from webapp.models import db

                db.create_all()
                yield client
                db.drop_all()

    def test_chat_requires_json_body(self, client):
        """Test that JSON body is required."""
        response = client.post("/api/chat")

        assert response.status_code == 400
        data = response.get_json()
        assert "JSON body required" in data["error"]

    def test_chat_requires_message(self, client):
        """Test that message is required."""
        response = client.post(
            "/api/chat",
            json={"other_field": "value"},
            content_type="application/json",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "Message is required" in data["error"]

    def test_chat_rejects_empty_message(self, client):
        """Test that empty message is rejected."""
        response = client.post(
            "/api/chat",
            json={"message": "   "},
            content_type="application/json",
        )

        assert response.status_code == 400

    def test_chat_rejects_long_message(self, client):
        """Test that overly long messages are rejected."""
        long_message = "x" * 33000

        response = client.post(
            "/api/chat",
            json={"message": long_message},
            content_type="application/json",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "too long" in data["error"].lower()

    def test_chat_validates_history_format(self, client):
        """Test that history format is validated."""
        response = client.post(
            "/api/chat",
            json={
                "message": "Hello",
                "history": "not a list",
            },
            content_type="application/json",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "must be a list" in data["error"]

    def test_chat_validates_history_entries(self, client):
        """Test that history entries are validated."""
        response = client.post(
            "/api/chat",
            json={
                "message": "Hello",
                "history": [{"invalid": "entry"}],
            },
            content_type="application/json",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "role" in data["error"] or "content" in data["error"]

    def test_chat_validates_history_roles(self, client):
        """Test that history roles are validated."""
        response = client.post(
            "/api/chat",
            json={
                "message": "Hello",
                "history": [{"role": "system", "content": "test"}],
            },
            content_type="application/json",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "user" in data["error"] or "assistant" in data["error"]

    def test_chat_success(self, client, app):
        """Test successful chat request."""
        with app.app_context():
            # Initialize services
            from webapp.ai import init_ai_client, init_chat_service

            init_ai_client(app)
            init_chat_service(app)

            response = client.post(
                "/api/chat",
                json={"message": "Hello, AI!"},
                content_type="application/json",
            )

            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
            assert "response" in data
            assert "skills_used" in data
            assert "usage" in data

    def test_chat_with_history(self, client, app):
        """Test chat with conversation history."""
        with app.app_context():
            from webapp.ai import init_ai_client, init_chat_service

            init_ai_client(app)
            init_chat_service(app)

            response = client.post(
                "/api/chat",
                json={
                    "message": "What about now?",
                    "history": [
                        {"role": "user", "content": "Hello"},
                        {"role": "assistant", "content": "Hi there!"},
                    ],
                },
                content_type="application/json",
            )

            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True

    def test_chat_service_unavailable(self, client, app):
        """Test response when chat service is not available."""
        with app.app_context():
            # Don't initialize chat service
            import webapp.ai.chat_service as chat_module

            chat_module._chat_service = None

            response = client.post(
                "/api/chat",
                json={"message": "Hello"},
                content_type="application/json",
            )

            assert response.status_code == 503
            data = response.get_json()
            assert "not available" in data["error"]


class TestSkillsPreviewEndpoint:
    """Tests for GET /api/chat/skills endpoint."""

    @pytest.fixture
    def app(self):
        """Create test Flask app."""
        from webapp.app import create_app
        from webapp.config import TestingConfig

        app = create_app(TestingConfig)
        app.config["TESTING"] = True
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        with app.test_client() as client:
            with app.app_context():
                from webapp.models import db

                db.create_all()
                yield client
                db.drop_all()

    def test_preview_requires_message(self, client):
        """Test that message query param is required."""
        response = client.get("/api/chat/skills")

        assert response.status_code == 400
        data = response.get_json()
        assert "required" in data["error"].lower()

    def test_preview_rejects_empty_message(self, client):
        """Test that empty message is rejected."""
        response = client.get("/api/chat/skills?message=   ")

        assert response.status_code == 400

    def test_preview_rejects_long_message(self, client):
        """Test that overly long messages are rejected."""
        long_message = "x" * 33000

        response = client.get(f"/api/chat/skills?message={long_message}")

        assert response.status_code == 400
        data = response.get_json()
        assert "too long" in data["error"].lower()

    def test_preview_success_no_matches(self, client, app):
        """Test successful preview with no skill matches."""
        with app.app_context():
            response = client.get("/api/chat/skills?message=random+text")

            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True
            assert "skills" in data
            assert data["message"] == "random text"

    def test_preview_works_without_chat_service(self, client, app):
        """Test that preview works even without chat service."""
        with app.app_context():
            # Ensure no chat service
            import webapp.ai.chat_service as chat_module

            chat_module._chat_service = None

            response = client.get("/api/chat/skills?message=test+message")

            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True


class TestChatEndpointWithSkills:
    """Tests for chat endpoint with skill matching."""

    @pytest.fixture
    def app(self):
        """Create test Flask app."""
        from webapp.app import create_app
        from webapp.config import TestingConfig

        app = create_app(TestingConfig)
        app.config["TESTING"] = True
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        with app.test_client() as client:
            with app.app_context():
                from webapp.models import db

                db.create_all()
                yield client
                db.drop_all()

    def test_chat_with_skill_trigger(self, client, app):
        """Test chat request that triggers a skill."""
        with app.app_context():
            from webapp.ai import init_ai_client, init_chat_service
            from webapp.skills.custom_skill_service import CustomSkillService
            from webapp.skills.r2_skill_loader import R2SkillLoader

            init_ai_client(app)
            init_chat_service(app)

            # Create a test skill in the database
            skill_content = """---
name: test_chat_skill
description: Test skill for chat
version: 1.0.0
triggers:
  - "run test chat"
---

# Test Chat Skill

Instructions for test.
"""
            mock_r2 = MagicMock(spec=R2SkillLoader)
            mock_r2.is_enabled = False
            service = CustomSkillService(r2_loader=mock_r2)

            service.create_skill(
                content=skill_content,
                scope="private",
                user_id="test_user",
                created_by="test_user",
            )

            # Note: Without proper auth integration, the skill won't match
            # This test verifies the endpoint works, actual skill matching
            # would require auth context
            response = client.post(
                "/api/chat",
                json={"message": "run test chat"},
                content_type="application/json",
            )

            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True


class TestChatErrorHandling:
    """Tests for chat endpoint error handling."""

    @pytest.fixture
    def app(self):
        """Create test Flask app."""
        from webapp.app import create_app
        from webapp.config import TestingConfig

        app = create_app(TestingConfig)
        app.config["TESTING"] = True
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        with app.test_client() as client:
            with app.app_context():
                from webapp.models import db

                db.create_all()
                yield client
                db.drop_all()

    def test_chat_handles_value_error(self, client, app):
        """Test that ValueError is handled properly."""
        with app.app_context():
            from webapp.ai import init_ai_client, init_chat_service, ChatService
            import webapp.ai.chat_service as chat_module

            init_ai_client(app)

            # Create a service that raises ValueError
            class BrokenService(ChatService):
                def send_message(self, *args, **kwargs):
                    raise ValueError("Test error")

            chat_module._chat_service = BrokenService()

            response = client.post(
                "/api/chat",
                json={"message": "Hello"},
                content_type="application/json",
            )

            assert response.status_code == 400
            data = response.get_json()
            assert "Test error" in data["error"]

    def test_chat_handles_unexpected_error(self, client, app):
        """Test that unexpected errors are handled properly."""
        with app.app_context():
            from webapp.ai import init_ai_client, ChatService
            import webapp.ai.chat_service as chat_module

            init_ai_client(app)

            # Create a service that raises unexpected error
            class BrokenService(ChatService):
                def send_message(self, *args, **kwargs):
                    raise RuntimeError("Unexpected error")

            chat_module._chat_service = BrokenService()

            response = client.post(
                "/api/chat",
                json={"message": "Hello"},
                content_type="application/json",
            )

            assert response.status_code == 500
            data = response.get_json()
            # Should not expose internal error details
            assert "An error occurred" in data["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
