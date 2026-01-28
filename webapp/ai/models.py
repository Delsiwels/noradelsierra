"""
AI Data Models

Dataclasses for AI responses and chat interactions.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AIResponse:
    """Response from an AI provider."""

    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class ChatResponse:
    """Response from the chat service with skill metadata."""

    content: str
    skills_used: list[str] = field(default_factory=list)
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
