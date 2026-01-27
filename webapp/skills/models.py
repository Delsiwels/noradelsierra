"""
Skills Data Models

Dataclasses for representing skills, their metadata, and content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class SkillMetadata:
    """Metadata from SKILL.md frontmatter."""

    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    last_verified: date | None = None
    tax_agent_approved: bool = False
    triggers: list[str] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class Skill:
    """A complete skill with metadata and content."""

    metadata: SkillMetadata
    content: str
    path: str
    guidelines: dict[str, str] = field(default_factory=dict)
    # Source tracking for multi-source registry
    source: str = "public"  # 'public', 'private', 'shared'
    owner_id: str | None = None  # user_id or team_id depending on source

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def description(self) -> str:
        return self.metadata.description

    @property
    def triggers(self) -> list[str]:
        return self.metadata.triggers

    @property
    def industries(self) -> list[str]:
        return self.metadata.industries

    def render_prompt(self, context: dict[str, Any] | None = None) -> str:
        """
        Render the skill content as a prompt, optionally with context.

        Args:
            context: Optional context dict with industry, transaction data, etc.

        Returns:
            The skill content with any context-specific guidelines appended.
        """
        prompt_parts = [self.content]

        if context:
            # Add industry-specific guidelines if available
            industry = context.get("industry")
            if industry and industry in self.guidelines:
                prompt_parts.append(
                    f"\n\n## Industry Guidelines ({industry.title()})\n"
                )
                prompt_parts.append(self.guidelines[industry])

        return "\n".join(prompt_parts)

    def get_guideline(self, industry: str) -> str | None:
        """Get industry-specific guideline content."""
        return self.guidelines.get(industry)

    def has_guideline(self, industry: str) -> bool:
        """Check if skill has guideline for given industry."""
        return industry in self.guidelines

    def to_dict(self) -> dict[str, Any]:
        """Convert skill to dictionary for API responses."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.metadata.version,
            "author": self.metadata.author,
            "triggers": self.triggers,
            "industries": self.industries,
            "tags": self.metadata.tags,
            "source": self.source,
            "owner_id": self.owner_id,
            "path": self.path,
        }


@dataclass
class SkillMatch:
    """Result of matching a user message to skills."""

    skill: Skill
    trigger: str
    confidence: float = 1.0
