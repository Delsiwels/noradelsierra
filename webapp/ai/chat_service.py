"""
Chat Service

Orchestrates skill injection with AI chat functionality.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .client import AIClient, get_ai_client
from .models import ChatResponse

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)

# Default system prompt
DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant."


class ChatService:
    """
    Service for skill-enhanced chat.

    Automatically detects skills from user messages and injects
    them into prompts before sending to the AI.
    """

    def __init__(
        self,
        ai_client: AIClient | None = None,
        skill_injector=None,
    ):
        """
        Initialize the chat service.

        Args:
            ai_client: AI client instance. Uses default if not provided.
            skill_injector: SkillInjector instance. Uses default if not provided.
        """
        self.ai_client = ai_client
        self._injector = skill_injector

    @property
    def injector(self):
        """Lazy load skill injector."""
        if self._injector is None:
            from webapp.skills import get_injector

            self._injector = get_injector()
        return self._injector

    def send_message(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        user_id: str | None = None,
        team_id: str | None = None,
        industry: str | None = None,
        base_prompt: str | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """
        Send a message with automatic skill injection.

        Args:
            user_message: The user's message
            conversation_history: Optional previous conversation messages
            user_id: Current user's ID (for private skill lookup)
            team_id: Current user's team ID (for shared skill lookup)
            industry: Industry context for skill guidelines
            base_prompt: Base system prompt (uses default if not provided)
            max_tokens: Optional max tokens override

        Returns:
            ChatResponse with content, skills_used, model, and usage

        Raises:
            ValueError: If AI client is not configured
        """
        if self.ai_client is None:
            raise ValueError(
                "AI client is not configured. "
                "Ensure ANTHROPIC_API_KEY is set or provide an ai_client."
            )

        # Build context for skill detection and injection
        context = {
            "user_message": user_message,
            "user_id": user_id,
            "team_id": team_id,
            "industry": industry,
        }

        # Detect matching skills
        matches = self.injector.detect_skill_triggers(user_message, user_id, team_id)

        # Limit to top 3 skills
        top_skills = [m.skill for m in matches[:3]]

        # Inject skills into the base prompt
        enhanced_prompt = self.injector.inject_skills(
            base_prompt or DEFAULT_SYSTEM_PROMPT,
            context,
            skills=top_skills,
        )

        # Build messages list
        messages = list(conversation_history) if conversation_history else []
        messages.append({"role": "user", "content": user_message})

        # Call AI
        kwargs = {}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        response = self.ai_client.chat_sync(messages, enhanced_prompt, **kwargs)

        # Log skill usage
        skill_names = [m.skill.name for m in matches[:3]]
        if skill_names:
            logger.info(f"Skills used for response: {skill_names}")

        return ChatResponse(
            content=response.content,
            skills_used=skill_names,
            model=response.model,
            usage=response.usage,
        )

    def preview_skills(
        self,
        user_message: str,
        user_id: str | None = None,
        team_id: str | None = None,
    ) -> list[dict]:
        """
        Preview which skills would be triggered by a message.

        Args:
            user_message: The message to check
            user_id: Current user's ID
            team_id: Current user's team ID

        Returns:
            List of skill info dicts with name, description, trigger, and confidence
        """
        matches = self.injector.detect_skill_triggers(user_message, user_id, team_id)

        return [
            {
                "name": m.skill.name,
                "description": m.skill.description,
                "trigger": m.trigger,
                "confidence": m.confidence,
                "source": m.skill.source,
            }
            for m in matches
        ]


# Module-level service instance
_chat_service: ChatService | None = None


def get_chat_service() -> ChatService | None:
    """Get the configured chat service singleton."""
    return _chat_service


def init_chat_service(app: Flask) -> ChatService | None:
    """
    Initialize the chat service from Flask app config.

    Args:
        app: Flask application instance

    Returns:
        Configured ChatService or None if AI client not configured
    """
    global _chat_service

    ai_client = get_ai_client()

    if ai_client is None:
        logger.warning(
            "Chat service not initialized: AI client not configured. "
            "Set ANTHROPIC_API_KEY to enable chat features."
        )
        return None

    _chat_service = ChatService(ai_client=ai_client)
    logger.info("Chat service initialized successfully")

    return _chat_service
