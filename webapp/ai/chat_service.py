"""
Chat Service

Orchestrates skill injection with AI chat functionality.
Supports both synchronous and streaming responses with optional persistence.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING

from .client import AIClient, get_ai_client
from .models import ChatResponse, StreamChunk

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

    Features:
    - Skill detection and injection
    - Synchronous and streaming responses
    - Conversation persistence
    - Token usage tracking
    - Skill usage analytics
    """

    def __init__(
        self,
        ai_client: AIClient | None = None,
        skill_injector=None,
        token_tracker=None,
        analytics_service=None,
    ):
        """
        Initialize the chat service.

        Args:
            ai_client: AI client instance. Uses default if not provided.
            skill_injector: SkillInjector instance. Uses default if not provided.
            token_tracker: TokenTracker instance. Uses default if not provided.
            analytics_service: SkillAnalyticsService instance. Uses default if not provided.
        """
        self.ai_client = ai_client
        self._injector = skill_injector
        self._token_tracker = token_tracker
        self._analytics_service = analytics_service

    @property
    def injector(self):
        """Lazy load skill injector."""
        if self._injector is None:
            from webapp.skills import get_injector

            self._injector = get_injector()
        return self._injector

    @property
    def token_tracker(self):
        """Lazy load token tracker."""
        if self._token_tracker is None:
            from webapp.ai.token_tracker import get_token_tracker

            self._token_tracker = get_token_tracker()
        return self._token_tracker

    @property
    def analytics_service(self):
        """Lazy load analytics service."""
        if self._analytics_service is None:
            from webapp.skills.analytics_service import get_analytics_service

            self._analytics_service = get_analytics_service()
        return self._analytics_service

    @staticmethod
    def _inject_bas_context(prompt: str, user_id: str) -> str:
        """Inject BAS deadline context into system prompt if deadline is near."""
        try:
            from webapp.services.bas_deadlines import get_bas_context_for_prompt

            context = get_bas_context_for_prompt(user_id)
            if context:
                return f"{prompt}\n\n{context}"
        except Exception as e:
            logger.debug(f"BAS context injection skipped: {e}")
        return prompt

    def _check_token_limit(self, user_id: str | None, team_id: str | None) -> None:
        """Check if user has available tokens. Raises if limit exceeded."""
        if user_id is None and team_id is None:
            return

        allowed, remaining = self.token_tracker.check_limit(user_id, team_id)
        if not allowed:
            from webapp.ai.token_tracker import TokenLimitExceededError

            raise TokenLimitExceededError(
                f"Token limit exceeded. Remaining tokens: {remaining}",
                remaining=remaining,
            )

    def _record_token_usage(
        self,
        user_id: str | None,
        team_id: str | None,
        usage: dict[str, int],
    ) -> None:
        """Record token usage after a request."""
        if user_id is None and team_id is None:
            return

        input_tokens = usage.get("input", 0)
        output_tokens = usage.get("output", 0)

        if input_tokens > 0 or output_tokens > 0:
            self.token_tracker.record_usage(
                user_id, team_id, input_tokens, output_tokens
            )

    def _log_skill_usage(
        self,
        matches: list,
        user_id: str | None,
        team_id: str | None,
        conversation_id: str | None,
    ) -> None:
        """Log skill usage for analytics."""
        if not matches:
            return

        try:
            for match in matches[:3]:  # Only top 3 skills are used
                self.analytics_service.log_usage(
                    skill_name=match.skill.name,
                    skill_source=match.skill.source,
                    user_id=user_id,
                    team_id=team_id,
                    trigger=match.trigger,
                    confidence=match.confidence,
                    conversation_id=conversation_id,
                )
        except Exception as e:
            logger.warning(f"Failed to log skill usage: {e}")

    def _persist_messages(
        self,
        conversation_id: str | None,
        user_id: str,
        user_message: str,
        assistant_content: str,
        model: str,
        skills_used: list[str],
        usage: dict[str, int],
    ) -> str:
        """Persist messages to database. Returns conversation_id."""
        from webapp.models import Conversation, Message, db

        # Get or create conversation
        conversation = None
        if conversation_id:
            conversation = db.session.get(Conversation, conversation_id)
            if not conversation or conversation.user_id != user_id:
                conversation = None

        if not conversation_id or not conversation:
            # Create new conversation
            conversation = Conversation(
                user_id=user_id,
                title=user_message[:100],  # First 100 chars as title
            )
            db.session.add(conversation)
            db.session.flush()

        # Add user message
        user_msg = Message(
            conversation_id=conversation.id,
            role="user",
            content=user_message,
        )
        db.session.add(user_msg)

        # Add assistant message
        assistant_msg = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=assistant_content,
            model=model,
            skills_used=skills_used,
            input_tokens=usage.get("input", 0),
            output_tokens=usage.get("output", 0),
        )
        db.session.add(assistant_msg)

        db.session.commit()

        return str(conversation.id)

    def send_message(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        user_id: str | None = None,
        team_id: str | None = None,
        industry: str | None = None,
        base_prompt: str | None = None,
        max_tokens: int | None = None,
        persist: bool = False,
        conversation_id: str | None = None,
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
            persist: Whether to persist the conversation
            conversation_id: Optional existing conversation ID

        Returns:
            ChatResponse with content, skills_used, model, and usage

        Raises:
            ValueError: If AI client is not configured
            TokenLimitExceededError: If token limit is exceeded
        """
        if self.ai_client is None:
            raise ValueError(
                "AI client is not configured. "
                "Ensure ANTHROPIC_API_KEY is set or provide an ai_client."
            )

        # Check token limit before making request
        self._check_token_limit(user_id, team_id)

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

        # Inject BAS deadline context if applicable
        if user_id:
            enhanced_prompt = self._inject_bas_context(enhanced_prompt, user_id)

        # Build messages list
        messages = list(conversation_history) if conversation_history else []
        messages.append({"role": "user", "content": user_message})

        # Call AI
        kwargs = {}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        response = self.ai_client.chat_sync(messages, enhanced_prompt, **kwargs)

        # Record token usage
        self._record_token_usage(user_id, team_id, response.usage)

        # Log skill usage
        skill_names = [m.skill.name for m in matches[:3]]
        if skill_names:
            logger.info(f"Skills used for response: {skill_names}")
            self._log_skill_usage(matches, user_id, team_id, conversation_id)

        # Persist if requested
        final_conversation_id = conversation_id
        if persist and user_id:
            final_conversation_id = self._persist_messages(
                conversation_id=conversation_id,
                user_id=user_id,
                user_message=user_message,
                assistant_content=response.content,
                model=response.model,
                skills_used=skill_names,
                usage=response.usage,
            )

        result = ChatResponse(
            content=response.content,
            skills_used=skill_names,
            model=response.model,
            usage=response.usage,
        )

        # Attach conversation_id if persisted
        if final_conversation_id:
            result.conversation_id = final_conversation_id

        return result

    def send_message_stream(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        user_id: str | None = None,
        team_id: str | None = None,
        industry: str | None = None,
        base_prompt: str | None = None,
        max_tokens: int | None = None,
        persist: bool = False,
        conversation_id: str | None = None,
    ) -> Iterator[StreamChunk]:
        """
        Stream a message response with automatic skill injection.

        Args:
            user_message: The user's message
            conversation_history: Optional previous conversation messages
            user_id: Current user's ID (for private skill lookup)
            team_id: Current user's team ID (for shared skill lookup)
            industry: Industry context for skill guidelines
            base_prompt: Base system prompt (uses default if not provided)
            max_tokens: Optional max tokens override
            persist: Whether to persist the conversation
            conversation_id: Optional existing conversation ID

        Yields:
            StreamChunk objects with partial content

        Raises:
            ValueError: If AI client is not configured
            TokenLimitExceededError: If token limit is exceeded
        """
        if self.ai_client is None:
            raise ValueError(
                "AI client is not configured. "
                "Ensure ANTHROPIC_API_KEY is set or provide an ai_client."
            )

        # Check token limit before making request
        self._check_token_limit(user_id, team_id)

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
        skill_names = [m.skill.name for m in matches[:3]]

        # Inject skills into the base prompt
        enhanced_prompt = self.injector.inject_skills(
            base_prompt or DEFAULT_SYSTEM_PROMPT,
            context,
            skills=top_skills,
        )

        # Inject BAS deadline context if applicable
        if user_id:
            enhanced_prompt = self._inject_bas_context(enhanced_prompt, user_id)

        # Build messages list
        messages = list(conversation_history) if conversation_history else []
        messages.append({"role": "user", "content": user_message})

        # Call AI with streaming
        kwargs = {}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        accumulated_content = ""
        final_usage = {}
        model = ""

        try:
            for chunk in self.ai_client.stream_chat(
                messages, enhanced_prompt, **kwargs
            ):
                accumulated_content += chunk.content
                model = chunk.model

                if chunk.done:
                    final_usage = chunk.usage

                    # Record token usage
                    self._record_token_usage(user_id, team_id, final_usage)

                    # Log skill usage
                    if skill_names:
                        logger.info(f"Skills used for response: {skill_names}")
                        self._log_skill_usage(
                            matches, user_id, team_id, conversation_id
                        )

                    # Persist if requested
                    if persist and user_id:
                        self._persist_messages(
                            conversation_id=conversation_id,
                            user_id=user_id,
                            user_message=user_message,
                            assistant_content=accumulated_content,
                            model=model,
                            skills_used=skill_names,
                            usage=final_usage,
                        )

                    # Yield final chunk with all metadata
                    yield StreamChunk(
                        content=chunk.content,
                        done=True,
                        model=model,
                        usage=final_usage,
                        skills_used=skill_names,
                    )
                else:
                    yield chunk

        except Exception as e:
            # Yield error chunk
            yield StreamChunk(
                content="",
                done=True,
                error=str(e),
            )
            raise

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
            "Set ANTHROPIC_API_KEY or OPENAI_API_KEY to enable chat features."
        )
        return None

    _chat_service = ChatService(ai_client=ai_client)
    logger.info("Chat service initialized successfully")

    return _chat_service
