"""
AI Client

Abstract base class and implementations for AI providers.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import TYPE_CHECKING

from .models import AIResponse, StreamChunk

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)


class AIClientError(Exception):
    """Base exception for AI client errors."""


class APIKeyMissingError(AIClientError):
    """Raised when API key is not configured."""


class RateLimitError(AIClientError):
    """Raised when rate limited by provider."""


class AIProviderError(AIClientError):
    """Raised when AI provider returns an error."""


class AIClient(ABC):
    """Abstract base class for AI clients."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        **kwargs,
    ) -> AIResponse:
        """
        Send a chat request asynchronously.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            system_prompt: Optional system prompt
            **kwargs: Additional provider-specific parameters

        Returns:
            AIResponse with content, model, and usage info
        """
        ...

    @abstractmethod
    def chat_sync(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        **kwargs,
    ) -> AIResponse:
        """
        Send a chat request synchronously.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            system_prompt: Optional system prompt
            **kwargs: Additional provider-specific parameters

        Returns:
            AIResponse with content, model, and usage info
        """
        ...

    @abstractmethod
    def stream_chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        **kwargs,
    ) -> Iterator[StreamChunk]:
        """
        Stream a chat response.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            system_prompt: Optional system prompt
            **kwargs: Additional provider-specific parameters

        Yields:
            StreamChunk objects with partial content
        """
        ...


class AnthropicClient(AIClient):
    """Anthropic Claude API client."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 2048,
    ):
        """
        Initialize the Anthropic client.

        Args:
            api_key: Anthropic API key (required for actual API calls)
            model: Model to use (default: claude-sonnet-4-20250514)
            max_tokens: Default max tokens for responses
        """
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self._client = None

    @property
    def client(self):
        """Lazy initialization of the Anthropic client."""
        if self._client is None:
            if not self.api_key:
                raise APIKeyMissingError(
                    "ANTHROPIC_API_KEY is not configured. "
                    "Set the environment variable or provide api_key parameter."
                )
            try:
                import anthropic

                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError as e:
                raise AIClientError(
                    "anthropic package not installed. "
                    "Install with: pip install anthropic"
                ) from e
        return self._client

    async def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        **kwargs,
    ) -> AIResponse:
        """
        Send a chat request asynchronously.

        Note: Currently wraps sync implementation. Use chat_sync for sync contexts.
        """
        return self.chat_sync(messages, system_prompt, **kwargs)

    def chat_sync(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        **kwargs,
    ) -> AIResponse:
        """
        Send a chat request synchronously.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            system_prompt: Optional system prompt
            **kwargs: Additional parameters (max_tokens, temperature, etc.)

        Returns:
            AIResponse with content, model, and usage info

        Raises:
            APIKeyMissingError: If API key is not configured
            RateLimitError: If rate limited by Anthropic
            AIProviderError: If Anthropic returns an error
        """
        max_tokens = kwargs.get("max_tokens", self.max_tokens)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt or "",
                messages=messages,
            )

            # Extract text content from response
            content = ""
            if response.content:
                content = response.content[0].text

            return AIResponse(
                content=content,
                model=self.model,
                usage={
                    "input": response.usage.input_tokens,
                    "output": response.usage.output_tokens,
                },
            )

        except Exception as e:
            error_str = str(e).lower()
            if "rate" in error_str and "limit" in error_str:
                raise RateLimitError(f"Rate limited by Anthropic: {e}") from e
            if "api key" in error_str or "authentication" in error_str:
                raise APIKeyMissingError(f"API key error: {e}") from e
            raise AIProviderError(f"Anthropic API error: {e}") from e

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        **kwargs,
    ) -> Iterator[StreamChunk]:
        """
        Stream a chat response.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            system_prompt: Optional system prompt
            **kwargs: Additional parameters

        Yields:
            StreamChunk objects with partial content
        """
        max_tokens = kwargs.get("max_tokens", self.max_tokens)

        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt or "",
                messages=messages,
            ) as stream:
                accumulated_content = ""

                for text in stream.text_stream:
                    accumulated_content += text
                    yield StreamChunk(
                        content=text,
                        done=False,
                        model=self.model,
                    )

                # Get final message for usage info
                final_message = stream.get_final_message()
                usage = {
                    "input": final_message.usage.input_tokens,
                    "output": final_message.usage.output_tokens,
                }

                yield StreamChunk(
                    content="",
                    done=True,
                    model=self.model,
                    usage=usage,
                )

        except Exception as e:
            error_str = str(e).lower()
            if "rate" in error_str and "limit" in error_str:
                raise RateLimitError(f"Rate limited by Anthropic: {e}") from e
            if "api key" in error_str or "authentication" in error_str:
                raise APIKeyMissingError(f"API key error: {e}") from e
            raise AIProviderError(f"Anthropic API error: {e}") from e


class MockAIClient(AIClient):
    """Mock AI client for testing."""

    def __init__(self, response_content: str = "Mock response"):
        """
        Initialize mock client.

        Args:
            response_content: Content to return in responses
        """
        self.response_content = response_content
        self.call_history: list[dict] = []

    async def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        **kwargs,
    ) -> AIResponse:
        """Record call and return mock response."""
        return self.chat_sync(messages, system_prompt, **kwargs)

    def chat_sync(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        **kwargs,
    ) -> AIResponse:
        """Record call and return mock response."""
        self.call_history.append(
            {
                "messages": messages,
                "system_prompt": system_prompt,
                "kwargs": kwargs,
            }
        )
        return AIResponse(
            content=self.response_content,
            model="mock-model",
            usage={"input": 10, "output": 20},
        )

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        **kwargs,
    ) -> Iterator[StreamChunk]:
        """Record call and yield mock streaming response."""
        self.call_history.append(
            {
                "messages": messages,
                "system_prompt": system_prompt,
                "kwargs": kwargs,
                "streaming": True,
            }
        )

        # Simulate streaming by yielding content in chunks
        words = self.response_content.split()
        for i, word in enumerate(words):
            content = word + (" " if i < len(words) - 1 else "")
            yield StreamChunk(
                content=content,
                done=False,
                model="mock-model",
            )

        # Final chunk with done=True and usage
        yield StreamChunk(
            content="",
            done=True,
            model="mock-model",
            usage={"input": 10, "output": 20},
        )


# Module-level client instance
_ai_client: AIClient | None = None


def get_ai_client() -> AIClient | None:
    """Get the configured AI client singleton."""
    return _ai_client


def init_ai_client(app: Flask) -> AIClient | None:
    """
    Initialize the AI client from Flask app config.

    Args:
        app: Flask application instance

    Returns:
        Configured AIClient or None if not configured

    Supports providers:
        - anthropic: Uses AnthropicClient with ANTHROPIC_API_KEY
        - openai: Uses OpenAIClient with OPENAI_API_KEY
    """
    global _ai_client

    provider = app.config.get("AI_PROVIDER", "anthropic")
    max_tokens = app.config.get("AI_MAX_TOKENS", 2048)

    # In testing mode, use mock client
    if app.config.get("TESTING"):
        _ai_client = MockAIClient()
        logger.info("AI client initialized with MockAIClient for testing")
        return _ai_client

    if provider == "anthropic":
        api_key = app.config.get("ANTHROPIC_API_KEY")
        model = app.config.get("AI_MODEL", "claude-sonnet-4-20250514")

        if not api_key:
            logger.warning(
                "ANTHROPIC_API_KEY not configured. AI features will be unavailable."
            )
            return None

        _ai_client = AnthropicClient(
            api_key=api_key,
            model=model,
            max_tokens=max_tokens,
        )
        logger.info(f"AI client initialized with Anthropic (model: {model})")

    elif provider == "openai":
        from .openai_client import OpenAIClient

        api_key = app.config.get("OPENAI_API_KEY")
        model = app.config.get("OPENAI_MODEL", "gpt-4-turbo-preview")

        if not api_key:
            logger.warning(
                "OPENAI_API_KEY not configured. AI features will be unavailable."
            )
            return None

        _ai_client = OpenAIClient(
            api_key=api_key,
            model=model,
            max_tokens=max_tokens,
        )
        logger.info(f"AI client initialized with OpenAI (model: {model})")

    elif provider == "deepseek":
        from .openai_client import OpenAIClient

        api_key = app.config.get("DEEPSEEK_API_KEY")
        model = app.config.get("DEEPSEEK_MODEL", "deepseek-chat")

        if not api_key:
            logger.warning(
                "DEEPSEEK_API_KEY not configured. AI features will be unavailable."
            )
            return None

        _ai_client = OpenAIClient(
            api_key=api_key,
            model=model,
            max_tokens=max_tokens,
            base_url="https://api.deepseek.com",
        )
        logger.info(f"AI client initialized with Deepseek (model: {model})")

    else:
        logger.warning(f"Unknown AI provider: {provider}")
        return None

    return _ai_client
