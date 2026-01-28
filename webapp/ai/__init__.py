"""
AI Module

Provides AI client abstraction and chat service for skill-enhanced conversations.

Usage:
    from webapp.ai import ChatService, get_chat_service
    from webapp.ai import AIClient, AnthropicClient, MockAIClient
    from webapp.ai import AIResponse, ChatResponse, StreamChunk

    # Get configured chat service
    service = get_chat_service()
    response = service.send_message("run a bas review")

    # Streaming response
    for chunk in service.send_message_stream("explain GST"):
        print(chunk.content, end="")

    # Or use AI client directly
    from webapp.ai import get_ai_client
    client = get_ai_client()
    response = client.chat_sync([{"role": "user", "content": "Hello"}])
"""

from .chat_service import ChatService, get_chat_service, init_chat_service
from .client import (
    AIClient,
    AIClientError,
    AIProviderError,
    AnthropicClient,
    APIKeyMissingError,
    MockAIClient,
    RateLimitError,
    get_ai_client,
    init_ai_client,
)
from .models import AIResponse, ChatResponse, StreamChunk
from .token_tracker import (
    TokenLimitExceededError,
    TokenTracker,
    get_token_tracker,
    init_token_tracker,
)

__all__ = [
    # Models
    "AIResponse",
    "ChatResponse",
    "StreamChunk",
    # Client classes
    "AIClient",
    "AnthropicClient",
    "MockAIClient",
    # Exceptions
    "AIClientError",
    "APIKeyMissingError",
    "RateLimitError",
    "AIProviderError",
    "TokenLimitExceededError",
    # Client functions
    "get_ai_client",
    "init_ai_client",
    # Chat service
    "ChatService",
    "get_chat_service",
    "init_chat_service",
    # Token tracker
    "TokenTracker",
    "get_token_tracker",
    "init_token_tracker",
]
