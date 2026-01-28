"""
OpenAI Client

Implementation of AIClient for OpenAI's API.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from .client import (
    AIClient,
    AIClientError,
    AIProviderError,
    APIKeyMissingError,
    RateLimitError,
)
from .models import AIResponse, StreamChunk

logger = logging.getLogger(__name__)

# Try to import OpenAI at module level for better testability
# This allows the class to be patched in tests
OpenAISDK = None
try:
    from openai import OpenAI as OpenAISDK  # type: ignore[no-redef,attr-defined]  # noqa: F401
except ImportError:
    pass


class OpenAIClient(AIClient):
    """OpenAI API client (also supports OpenAI-compatible APIs like Deepseek)."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4-turbo-preview",
        max_tokens: int = 2048,
        base_url: str | None = None,
    ):
        """
        Initialize the OpenAI client.

        Args:
            api_key: OpenAI API key (required for actual API calls)
            model: Model to use (default: gpt-4-turbo-preview)
            max_tokens: Default max tokens for responses
            base_url: Optional custom base URL for OpenAI-compatible APIs
        """
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.base_url = base_url
        self._client = None

    @property
    def client(self):
        """Lazy initialization of the OpenAI client."""
        if self._client is None:
            if not self.api_key:
                raise APIKeyMissingError(
                    "API key is not configured. "
                    "Set the environment variable or provide api_key parameter."
                )
            if OpenAISDK is None:
                raise AIClientError(
                    "openai package not installed. " "Install with: pip install openai"
                )
            if self.base_url:
                self._client = OpenAISDK(api_key=self.api_key, base_url=self.base_url)
            else:
                self._client = OpenAISDK(api_key=self.api_key)
        return self._client

    async def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        **kwargs,
    ) -> AIResponse:
        """
        Send a chat request asynchronously.

        Note: Currently wraps sync implementation.
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
            system_prompt: Optional system prompt (prepended as system message)
            **kwargs: Additional parameters (max_tokens, temperature, etc.)

        Returns:
            AIResponse with content, model, and usage info

        Raises:
            APIKeyMissingError: If API key is not configured
            RateLimitError: If rate limited by OpenAI
            AIProviderError: If OpenAI returns an error
        """
        max_tokens = kwargs.get("max_tokens", self.max_tokens)

        # Build messages list with system prompt
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=all_messages,
                max_tokens=max_tokens,
                temperature=kwargs.get("temperature", 1.0),
            )

            content = response.choices[0].message.content or ""

            return AIResponse(
                content=content,
                model=self.model,
                usage={
                    "input": response.usage.prompt_tokens,
                    "output": response.usage.completion_tokens,
                },
            )

        except Exception as e:
            error_str = str(e).lower()
            if "rate" in error_str and "limit" in error_str:
                raise RateLimitError(f"Rate limited by OpenAI: {e}") from e
            if (
                "api key" in error_str
                or "authentication" in error_str
                or "invalid" in error_str
            ):
                raise APIKeyMissingError(f"API key error: {e}") from e
            raise AIProviderError(f"OpenAI API error: {e}") from e

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

        # Build messages list with system prompt
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=all_messages,
                max_tokens=max_tokens,
                temperature=kwargs.get("temperature", 1.0),
                stream=True,
                stream_options={"include_usage": True},
            )

            accumulated_content = ""
            usage = {"input": 0, "output": 0}

            for chunk in stream:
                # Handle content chunks
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    accumulated_content += content
                    yield StreamChunk(
                        content=content,
                        done=False,
                        model=self.model,
                    )

                # Handle usage info (comes at the end)
                if chunk.usage:
                    usage = {
                        "input": chunk.usage.prompt_tokens,
                        "output": chunk.usage.completion_tokens,
                    }

                # Check for stream end
                if chunk.choices and chunk.choices[0].finish_reason:
                    yield StreamChunk(
                        content="",
                        done=True,
                        model=self.model,
                        usage=usage,
                    )

        except Exception as e:
            error_str = str(e).lower()
            if "rate" in error_str and "limit" in error_str:
                raise RateLimitError(f"Rate limited by OpenAI: {e}") from e
            if "api key" in error_str or "authentication" in error_str:
                raise APIKeyMissingError(f"API key error: {e}") from e
            raise AIProviderError(f"OpenAI API error: {e}") from e
