"""
Tests for AI Client Module

Tests cover:
- AIResponse and ChatResponse dataclasses
- MockAIClient functionality
- AnthropicClient initialization and error handling
- Client singleton management
"""

import pytest
from unittest.mock import MagicMock, patch


class TestAIResponse:
    """Tests for AIResponse dataclass."""

    def test_create_response(self):
        """Test creating an AIResponse."""
        from webapp.ai import AIResponse

        response = AIResponse(
            content="Hello, world!",
            model="claude-sonnet-4-20250514",
            usage={"input": 10, "output": 20},
        )

        assert response.content == "Hello, world!"
        assert response.model == "claude-sonnet-4-20250514"
        assert response.usage["input"] == 10
        assert response.usage["output"] == 20

    def test_default_usage(self):
        """Test AIResponse with default usage."""
        from webapp.ai import AIResponse

        response = AIResponse(
            content="Test",
            model="test-model",
        )

        assert response.usage == {}


class TestChatResponse:
    """Tests for ChatResponse dataclass."""

    def test_create_chat_response(self):
        """Test creating a ChatResponse."""
        from webapp.ai import ChatResponse

        response = ChatResponse(
            content="I can help with that BAS review.",
            skills_used=["bas_review", "tax_compliance"],
            model="claude-sonnet-4-20250514",
            usage={"input": 50, "output": 100},
        )

        assert response.content == "I can help with that BAS review."
        assert "bas_review" in response.skills_used
        assert len(response.skills_used) == 2
        assert response.model == "claude-sonnet-4-20250514"

    def test_default_values(self):
        """Test ChatResponse with default values."""
        from webapp.ai import ChatResponse

        response = ChatResponse(content="Simple response")

        assert response.content == "Simple response"
        assert response.skills_used == []
        assert response.model == ""
        assert response.usage == {}


class TestMockAIClient:
    """Tests for MockAIClient."""

    def test_chat_sync(self):
        """Test synchronous chat call."""
        from webapp.ai import MockAIClient

        client = MockAIClient(response_content="Test response")
        response = client.chat_sync(
            [{"role": "user", "content": "Hello"}],
            system_prompt="You are helpful",
        )

        assert response.content == "Test response"
        assert response.model == "mock-model"
        assert response.usage["input"] == 10
        assert response.usage["output"] == 20

    def test_records_call_history(self):
        """Test that calls are recorded in history."""
        from webapp.ai import MockAIClient

        client = MockAIClient()
        messages = [{"role": "user", "content": "Test"}]
        system_prompt = "Be helpful"

        client.chat_sync(messages, system_prompt)
        client.chat_sync(messages, system_prompt, max_tokens=1000)

        assert len(client.call_history) == 2
        assert client.call_history[0]["messages"] == messages
        assert client.call_history[0]["system_prompt"] == system_prompt
        assert client.call_history[1]["kwargs"]["max_tokens"] == 1000

    def test_chat_async_via_sync(self):
        """Test async chat call (via sync wrapper since async wraps sync)."""
        import asyncio

        from webapp.ai import MockAIClient

        client = MockAIClient(response_content="Async response")

        # Run the async method using asyncio
        async def run_async():
            return await client.chat([{"role": "user", "content": "Hello"}])

        response = asyncio.run(run_async())

        assert response.content == "Async response"


class TestAnthropicClient:
    """Tests for AnthropicClient."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        from webapp.ai import AnthropicClient

        client = AnthropicClient(api_key="test-key")

        assert client.api_key == "test-key"
        assert client.model == "claude-sonnet-4-20250514"
        assert client.max_tokens == 2048

    def test_init_with_custom_values(self):
        """Test initialization with custom values."""
        from webapp.ai import AnthropicClient

        client = AnthropicClient(
            api_key="test-key",
            model="claude-opus-4-20250514",
            max_tokens=4096,
        )

        assert client.model == "claude-opus-4-20250514"  # gitleaks:allow
        assert client.max_tokens == 4096

    def test_missing_api_key_raises_error(self):
        """Test that missing API key raises error on use."""
        from webapp.ai import AnthropicClient, APIKeyMissingError

        client = AnthropicClient(api_key=None)

        with pytest.raises(APIKeyMissingError):
            _ = client.client  # Access client property

    def test_chat_sync_with_mock(self):
        """Test chat_sync with mocked anthropic client."""
        from webapp.ai import AnthropicClient

        client = AnthropicClient(api_key="test-key")

        # Mock the anthropic module
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Mocked response")]
        mock_response.usage.input_tokens = 15
        mock_response.usage.output_tokens = 25

        mock_anthropic_client = MagicMock()
        mock_anthropic_client.messages.create.return_value = mock_response
        client._client = mock_anthropic_client

        response = client.chat_sync(
            [{"role": "user", "content": "Hello"}],
            system_prompt="Be helpful",
        )

        assert response.content == "Mocked response"
        assert response.usage["input"] == 15
        assert response.usage["output"] == 25

        # Verify call was made correctly
        mock_anthropic_client.messages.create.assert_called_once_with(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system="Be helpful",
            messages=[{"role": "user", "content": "Hello"}],
        )

    def test_chat_sync_with_max_tokens_override(self):
        """Test chat_sync with max_tokens parameter override."""
        from webapp.ai import AnthropicClient

        client = AnthropicClient(api_key="test-key", max_tokens=1024)

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Response")]
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 20

        mock_anthropic_client = MagicMock()
        mock_anthropic_client.messages.create.return_value = mock_response
        client._client = mock_anthropic_client

        client.chat_sync(
            [{"role": "user", "content": "Hello"}],
            max_tokens=500,
        )

        # Verify override was used
        call_kwargs = mock_anthropic_client.messages.create.call_args[1]
        assert call_kwargs["max_tokens"] == 500


class TestClientExceptions:
    """Tests for AI client exceptions."""

    def test_rate_limit_error(self):
        """Test RateLimitError exception."""
        from webapp.ai import RateLimitError, AIClientError

        error = RateLimitError("Rate limited")
        assert isinstance(error, AIClientError)
        assert "Rate limited" in str(error)

    def test_api_key_missing_error(self):
        """Test APIKeyMissingError exception."""
        from webapp.ai import APIKeyMissingError, AIClientError

        error = APIKeyMissingError("No API key")
        assert isinstance(error, AIClientError)

    def test_ai_provider_error(self):
        """Test AIProviderError exception."""
        from webapp.ai import AIProviderError, AIClientError

        error = AIProviderError("Provider error")
        assert isinstance(error, AIClientError)


class TestClientSingleton:
    """Tests for AI client singleton management."""

    @pytest.fixture
    def app(self):
        """Create test Flask app."""
        from webapp.app import create_app
        from webapp.config import TestingConfig

        app = create_app(TestingConfig)
        return app

    def test_init_ai_client_testing_mode(self, app):
        """Test that testing mode uses MockAIClient."""
        from webapp.ai import MockAIClient
        from webapp.ai.client import _ai_client, init_ai_client

        with app.app_context():
            client = init_ai_client(app)

            assert client is not None
            assert isinstance(client, MockAIClient)

    def test_get_ai_client_returns_singleton(self, app):
        """Test that get_ai_client returns the singleton."""
        from webapp.ai import get_ai_client, init_ai_client

        with app.app_context():
            init_ai_client(app)
            client1 = get_ai_client()
            client2 = get_ai_client()

            assert client1 is client2

    def test_init_without_api_key_returns_none(self):
        """Test that missing API key returns None in non-testing mode."""
        from flask import Flask
        from webapp.ai.client import init_ai_client

        app = Flask(__name__)
        app.config["TESTING"] = False
        app.config["AI_PROVIDER"] = "anthropic"
        app.config["ANTHROPIC_API_KEY"] = None

        client = init_ai_client(app)

        assert client is None

    def test_unknown_provider_returns_none(self):
        """Test that unknown provider returns None."""
        from flask import Flask
        from webapp.ai.client import init_ai_client

        app = Flask(__name__)
        app.config["TESTING"] = False
        app.config["AI_PROVIDER"] = "unknown_provider"
        app.config["ANTHROPIC_API_KEY"] = "test-key"

        client = init_ai_client(app)

        assert client is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
