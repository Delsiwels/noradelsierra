"""Tests for OpenAI client implementation."""

from unittest.mock import MagicMock, patch

import pytest

from webapp.ai.client import AIProviderError, APIKeyMissingError, RateLimitError
from webapp.ai.models import AIResponse
from webapp.ai.openai_client import OpenAIClient


class TestOpenAIClient:
    """Tests for OpenAIClient class."""

    def test_init_default_values(self):
        """Test initialization with default values."""
        client = OpenAIClient(api_key="test-key")

        assert client.api_key == "test-key"
        assert client.model == "gpt-4-turbo-preview"
        assert client.max_tokens == 2048
        assert client._client is None

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        client = OpenAIClient(
            api_key="custom-key",
            model="gpt-4o",
            max_tokens=4096,
        )

        assert client.api_key == "custom-key"
        assert client.model == "gpt-4o"
        assert client.max_tokens == 4096

    def test_client_property_requires_api_key(self):
        """Test that accessing client property without API key raises error."""
        client = OpenAIClient(api_key=None)

        with pytest.raises(APIKeyMissingError) as exc_info:
            _ = client.client

        assert "API key is not configured" in str(exc_info.value)

    @patch("webapp.ai.openai_client.OpenAISDK")
    def test_client_lazy_initialization(self, mock_openai):
        """Test that client is lazily initialized."""
        client = OpenAIClient(api_key="test-key")

        # Client not initialized yet
        mock_openai.assert_not_called()

        # Access client property
        _ = client.client

        # Now it should be initialized
        mock_openai.assert_called_once_with(api_key="test-key")

    @patch("webapp.ai.openai_client.OpenAISDK")
    def test_chat_sync_success(self, mock_openai):
        """Test successful synchronous chat."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test response"))]
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = OpenAIClient(api_key="test-key")

        messages = [{"role": "user", "content": "Hello"}]
        response = client.chat_sync(messages, system_prompt="You are helpful")

        assert isinstance(response, AIResponse)
        assert response.content == "Test response"
        assert response.model == "gpt-4-turbo-preview"
        assert response.usage == {"input": 10, "output": 20}

        # Verify API call
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert len(call_kwargs["messages"]) == 2  # System + user
        assert call_kwargs["messages"][0]["role"] == "system"

    @patch("webapp.ai.openai_client.OpenAISDK")
    def test_chat_sync_without_system_prompt(self, mock_openai):
        """Test chat without system prompt."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Response"))]
        mock_response.usage.prompt_tokens = 5
        mock_response.usage.completion_tokens = 10

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = OpenAIClient(api_key="test-key")
        messages = [{"role": "user", "content": "Hello"}]

        client.chat_sync(messages)

        # No system message prepended
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert len(call_kwargs["messages"]) == 1

    @patch("webapp.ai.openai_client.OpenAISDK")
    def test_chat_sync_rate_limit_error(self, mock_openai):
        """Test rate limit handling."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception(
            "Rate limit exceeded"
        )
        mock_openai.return_value = mock_client

        client = OpenAIClient(api_key="test-key")

        with pytest.raises(RateLimitError):
            client.chat_sync([{"role": "user", "content": "Hello"}])

    @patch("webapp.ai.openai_client.OpenAISDK")
    def test_chat_sync_api_key_error(self, mock_openai):
        """Test API key error handling."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Invalid API key")
        mock_openai.return_value = mock_client

        client = OpenAIClient(api_key="test-key")

        with pytest.raises(APIKeyMissingError):
            client.chat_sync([{"role": "user", "content": "Hello"}])

    @patch("webapp.ai.openai_client.OpenAISDK")
    def test_chat_sync_generic_error(self, mock_openai):
        """Test generic error handling."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Unknown error")
        mock_openai.return_value = mock_client

        client = OpenAIClient(api_key="test-key")

        with pytest.raises(AIProviderError):
            client.chat_sync([{"role": "user", "content": "Hello"}])

    @patch("webapp.ai.openai_client.OpenAISDK")
    def test_chat_async_wraps_sync(self, mock_openai):
        """Test that async chat wraps sync implementation."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Response"))]
        mock_response.usage.prompt_tokens = 5
        mock_response.usage.completion_tokens = 10

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = OpenAIClient(api_key="test-key")

        import asyncio

        response = asyncio.run(client.chat([{"role": "user", "content": "Hello"}]))

        assert isinstance(response, AIResponse)
        assert response.content == "Response"

    @patch("webapp.ai.openai_client.OpenAISDK")
    def test_stream_chat_success(self, mock_openai):
        """Test streaming chat response."""
        # Create mock stream chunks
        chunk1 = MagicMock()
        chunk1.choices = [
            MagicMock(delta=MagicMock(content="Hello "), finish_reason=None)
        ]
        chunk1.usage = None

        chunk2 = MagicMock()
        chunk2.choices = [
            MagicMock(delta=MagicMock(content="world"), finish_reason=None)
        ]
        chunk2.usage = None

        chunk3 = MagicMock()
        chunk3.choices = [
            MagicMock(delta=MagicMock(content=None), finish_reason="stop")
        ]
        chunk3.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = iter(
            [chunk1, chunk2, chunk3]
        )
        mock_openai.return_value = mock_client

        client = OpenAIClient(api_key="test-key")

        chunks = list(client.stream_chat([{"role": "user", "content": "Hi"}]))

        assert len(chunks) >= 2  # At least content chunks + final
        assert any(c.content == "Hello " for c in chunks)
        assert any(c.done for c in chunks)

    @patch("webapp.ai.openai_client.OpenAISDK")
    def test_stream_chat_with_system_prompt(self, mock_openai):
        """Test streaming with system prompt."""
        chunk = MagicMock()
        chunk.choices = [MagicMock(delta=MagicMock(content=None), finish_reason="stop")]
        chunk.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = iter([chunk])
        mock_openai.return_value = mock_client

        client = OpenAIClient(api_key="test-key")

        list(
            client.stream_chat(
                [{"role": "user", "content": "Hi"}],
                system_prompt="Be helpful",
            )
        )

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["messages"][0]["role"] == "system"
        assert call_kwargs["stream"] is True

    def test_custom_max_tokens_in_chat(self):
        """Test that max_tokens can be overridden in chat calls."""
        with patch("webapp.ai.openai_client.OpenAISDK") as mock_openai:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content="OK"))]
            mock_response.usage.prompt_tokens = 5
            mock_response.usage.completion_tokens = 1

            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client

            client = OpenAIClient(api_key="test-key", max_tokens=1000)

            client.chat_sync([{"role": "user", "content": "Hi"}], max_tokens=500)

            call_kwargs = mock_client.chat.completions.create.call_args.kwargs
            assert call_kwargs["max_tokens"] == 500
