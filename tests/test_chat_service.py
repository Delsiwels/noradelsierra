"""
Tests for Chat Service

Tests cover:
- ChatService initialization
- Message sending with skill injection
- Skill preview functionality
- Error handling
- Service singleton management
"""

from unittest.mock import MagicMock

import pytest

# Test skill content
VALID_SKILL_CONTENT = """---
name: test_skill
description: A test skill for unit testing
version: 1.0.0
triggers:
  - "run test"
  - "execute test"
---

# Test Skill

This is a test skill for unit testing purposes.
"""


class TestChatService:
    """Tests for ChatService class."""

    @pytest.fixture
    def mock_ai_client(self):
        """Create a mock AI client."""
        from webapp.ai import MockAIClient

        return MockAIClient(response_content="Test AI response")

    @pytest.fixture
    def mock_injector(self):
        """Create a mock skill injector."""
        mock = MagicMock()
        mock.detect_skill_triggers.return_value = []
        mock.inject_skills.return_value = "Enhanced prompt"
        return mock

    def test_init_with_client(self, mock_ai_client, mock_injector):
        """Test initialization with explicit client."""
        from webapp.ai import ChatService

        service = ChatService(
            ai_client=mock_ai_client,
            skill_injector=mock_injector,
        )

        assert service.ai_client is mock_ai_client
        assert service._injector is mock_injector

    def test_send_message_basic(self, mock_ai_client, mock_injector):
        """Test basic message sending."""
        from webapp.ai import ChatService

        service = ChatService(
            ai_client=mock_ai_client,
            skill_injector=mock_injector,
        )

        response = service.send_message("Hello, AI!")

        assert response.content == "Test AI response"
        assert response.skills_used == []
        assert response.model == "mock-model"
        assert response.usage["input"] == 10

    def test_send_message_with_skill_match(self, app, mock_ai_client):
        """Test message sending with skill matching."""
        from webapp.ai import ChatService
        from webapp.skills.models import Skill, SkillMatch, SkillMetadata

        # Create a mock skill
        mock_skill = Skill(
            metadata=SkillMetadata(
                name="bas_review",
                description="BAS Review skill",
                triggers=["run bas review"],
            ),
            content="BAS instructions",
            path="test",
        )

        mock_match = SkillMatch(
            skill=mock_skill,
            trigger="run bas review",
            confidence=0.9,
        )

        mock_injector = MagicMock()
        mock_injector.detect_skill_triggers.return_value = [mock_match]
        mock_injector.inject_skills.return_value = "Enhanced prompt"

        service = ChatService(
            ai_client=mock_ai_client,
            skill_injector=mock_injector,
        )

        response = service.send_message(
            "Please run bas review",
            user_id="user123",
            team_id="team456",
        )

        assert response.skills_used == ["bas_review"]
        mock_injector.detect_skill_triggers.assert_called_once_with(
            "Please run bas review", "user123", "team456"
        )

    def test_send_message_with_history(self, mock_ai_client, mock_injector):
        """Test message sending with conversation history."""
        from webapp.ai import ChatService

        service = ChatService(
            ai_client=mock_ai_client,
            skill_injector=mock_injector,
        )

        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        service.send_message("What about that?", conversation_history=history)

        # Check the AI client was called with history + new message
        assert len(mock_ai_client.call_history) == 1
        messages = mock_ai_client.call_history[0]["messages"]
        assert len(messages) == 3
        assert messages[0]["content"] == "Hello"
        assert messages[1]["content"] == "Hi there!"
        assert messages[2]["content"] == "What about that?"

    def test_send_message_with_custom_prompt(self, mock_ai_client, mock_injector):
        """Test message sending with custom base prompt."""
        from webapp.ai import ChatService

        service = ChatService(
            ai_client=mock_ai_client,
            skill_injector=mock_injector,
        )

        custom_prompt = "You are a specialized tax assistant."
        service.send_message("Help me", base_prompt=custom_prompt)

        mock_injector.inject_skills.assert_called_once()
        call_args = mock_injector.inject_skills.call_args
        assert call_args[0][0] == custom_prompt

    def test_send_message_limits_skills(self, mock_ai_client):
        """Test that only top 3 skills are used."""
        from webapp.ai import ChatService
        from webapp.skills.models import Skill, SkillMatch, SkillMetadata

        # Create 5 mock skills
        mock_matches = []
        for i in range(5):
            skill = Skill(
                metadata=SkillMetadata(
                    name=f"skill_{i}",
                    description=f"Skill {i}",
                    triggers=[f"trigger {i}"],
                ),
                content="Content",
                path="test",
            )
            mock_matches.append(
                SkillMatch(
                    skill=skill, trigger=f"trigger {i}", confidence=0.9 - i * 0.1
                )
            )

        mock_injector = MagicMock()
        mock_injector.detect_skill_triggers.return_value = mock_matches
        mock_injector.inject_skills.return_value = "Enhanced"

        service = ChatService(
            ai_client=mock_ai_client,
            skill_injector=mock_injector,
        )

        response = service.send_message("Test")

        # Only top 3 should be used
        assert len(response.skills_used) == 3
        assert response.skills_used == ["skill_0", "skill_1", "skill_2"]

    def test_send_message_without_client_raises(self, mock_injector):
        """Test that missing AI client raises ValueError."""
        from webapp.ai import ChatService

        service = ChatService(
            ai_client=None,
            skill_injector=mock_injector,
        )

        with pytest.raises(ValueError, match="AI client is not configured"):
            service.send_message("Hello")

    def test_preview_skills(self, mock_ai_client):
        """Test skill preview functionality."""
        from webapp.ai import ChatService
        from webapp.skills.models import Skill, SkillMatch, SkillMetadata

        mock_skill = Skill(
            metadata=SkillMetadata(
                name="bas_review",
                description="BAS Review skill",
                triggers=["run bas review"],
            ),
            content="Content",
            path="test",
            source="public",
        )

        mock_match = SkillMatch(
            skill=mock_skill,
            trigger="run bas review",
            confidence=0.85,
        )

        mock_injector = MagicMock()
        mock_injector.detect_skill_triggers.return_value = [mock_match]

        service = ChatService(
            ai_client=mock_ai_client,
            skill_injector=mock_injector,
        )

        preview = service.preview_skills("run bas review", "user123", "team456")

        assert len(preview) == 1
        assert preview[0]["name"] == "bas_review"
        assert preview[0]["description"] == "BAS Review skill"
        assert preview[0]["trigger"] == "run bas review"
        assert preview[0]["confidence"] == 0.85
        assert preview[0]["source"] == "public"

    def test_preview_skills_no_matches(self, mock_ai_client, mock_injector):
        """Test skill preview with no matches."""
        from webapp.ai import ChatService

        service = ChatService(
            ai_client=mock_ai_client,
            skill_injector=mock_injector,
        )

        preview = service.preview_skills("random message")

        assert preview == []


class TestChatServiceIntegration:
    """Integration tests for ChatService with real SkillInjector."""

    @pytest.fixture
    def app(self):
        """Create test Flask app."""
        from webapp.app import create_app
        from webapp.config import TestingConfig

        app = create_app(TestingConfig)
        return app

    def test_real_skill_injection(self, app):
        """Test with real skill injector (no matches expected without skills)."""
        from webapp.ai import ChatService, MockAIClient
        from webapp.skills import SkillInjector

        with app.app_context():
            from webapp.models import db

            db.create_all()

            client = MockAIClient(response_content="AI Response")
            injector = SkillInjector()

            service = ChatService(
                ai_client=client,
                skill_injector=injector,
            )

            response = service.send_message("Hello, how are you?")

            assert response.content == "AI Response"
            assert response.skills_used == []

            db.drop_all()


class TestChatServiceSingleton:
    """Tests for chat service singleton management."""

    @pytest.fixture
    def app(self):
        """Create test Flask app."""
        from webapp.app import create_app
        from webapp.config import TestingConfig

        app = create_app(TestingConfig)
        return app

    def test_init_chat_service(self, app):
        """Test chat service initialization."""
        from webapp.ai import ChatService, init_chat_service
        from webapp.ai.client import init_ai_client

        with app.app_context():
            # Initialize AI client first
            init_ai_client(app)

            service = init_chat_service(app)

            assert service is not None
            assert isinstance(service, ChatService)

    def test_get_chat_service_returns_singleton(self, app):
        """Test that get_chat_service returns the singleton."""
        from webapp.ai import get_chat_service, init_chat_service
        from webapp.ai.client import init_ai_client

        with app.app_context():
            init_ai_client(app)
            init_chat_service(app)

            service1 = get_chat_service()
            service2 = get_chat_service()

            assert service1 is service2

    def test_init_without_ai_client_returns_none(self, app):
        """Test that missing AI client returns None."""
        import webapp.ai.client as client_module
        from webapp.ai.chat_service import init_chat_service

        with app.app_context():
            # Ensure no AI client
            client_module._ai_client = None

            service = init_chat_service(app)

            assert service is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
