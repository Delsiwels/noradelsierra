"""
Skill Injector

Injects relevant skills into AI prompts based on context and user messages.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .models import Skill, SkillMatch
from .skill_registry import SkillRegistry, get_registry

logger = logging.getLogger(__name__)


class SkillInjector:
    """
    Injects relevant skills into AI prompts.

    Detects skill triggers in user messages and injects appropriate
    skill instructions into the base prompt.

    Usage:
        injector = SkillInjector()
        enhanced_prompt = injector.inject_skills(base_prompt, context)
    """

    def __init__(self, registry: SkillRegistry | None = None):
        """
        Initialize the skill injector.

        Args:
            registry: Optional SkillRegistry instance. Uses default if not provided.
        """
        self.registry = registry or get_registry()

    def detect_skill_triggers(
        self,
        user_message: str,
        user_id: str | None = None,
        team_id: str | None = None,
    ) -> list[SkillMatch]:
        """
        Match user intent to skill triggers.

        Searches all sources with priority: private > shared > public.

        Args:
            user_message: The user's message
            user_id: Current user's ID (for private skill lookup)
            team_id: Current user's team ID (for shared skill lookup)

        Returns:
            List of SkillMatch objects for matching skills
        """
        message_lower = user_message.lower()
        matches = []
        seen_names: set[str] = set()

        # Get all skills with priority ordering
        all_skills = self.registry.discover_all_skills(user_id, team_id)

        # Check in priority order
        for source in ["private", "shared", "public"]:
            for skill in all_skills[source]:
                # Skip if already matched by higher priority source
                if skill.name in seen_names:
                    continue

                for trigger in skill.triggers:
                    trigger_lower = trigger.lower()
                    if self._matches_trigger(message_lower, trigger_lower):
                        matches.append(
                            SkillMatch(
                                skill=skill,
                                trigger=trigger,
                                confidence=self._calculate_confidence(
                                    message_lower, trigger_lower
                                ),
                            )
                        )
                        seen_names.add(skill.name)
                        break  # One match per skill is enough

        # Sort by confidence descending
        matches.sort(key=lambda m: m.confidence, reverse=True)

        return matches

    def _matches_trigger(self, message: str, trigger: str) -> bool:
        """
        Check if message matches a trigger pattern.

        Supports:
        - Exact substring match
        - Word boundary matching for short triggers
        """
        # Direct substring match
        if trigger in message:
            return True

        # Word-based matching for triggers with multiple words
        trigger_words = trigger.split()
        if len(trigger_words) > 1:
            # Check if all words appear in order (not necessarily adjacent)
            pattern = r".*".join(re.escape(word) for word in trigger_words)
            if re.search(pattern, message):
                return True

        return False

    def _calculate_confidence(self, message: str, trigger: str) -> float:
        """
        Calculate confidence score for a trigger match.

        Returns:
            Float between 0.0 and 1.0
        """
        # Exact match is highest confidence
        if trigger == message.strip():
            return 1.0

        # Starts with trigger
        if message.strip().startswith(trigger):
            return 0.9

        # Contains trigger as substring
        if trigger in message:
            # Higher confidence for longer triggers
            return min(0.8, 0.5 + len(trigger) / 100)

        # Partial word match
        return 0.3

    def inject_skills(
        self,
        base_prompt: str,
        context: dict[str, Any] | None = None,
        skills: list[Skill] | None = None,
        max_skills: int = 3,
    ) -> str:
        """
        Add skill instructions to prompt based on context.

        Args:
            base_prompt: The original system prompt
            context: Optional context dict with:
                - user_message: The user's message (used for trigger detection)
                - user_id: Current user ID (for private skill lookup)
                - team_id: Current team ID (for shared skill lookup)
                - industry: Industry for guidelines
                - Other context passed to skill rendering
            skills: Optional list of skills to inject. If not provided,
                   skills are detected from context['user_message']
            max_skills: Maximum number of skills to inject

        Returns:
            Enhanced prompt with skill instructions
        """
        context = context or {}

        # Detect skills from user message if not explicitly provided
        if skills is None:
            user_message = context.get("user_message", "")
            if user_message:
                user_id = context.get("user_id")
                team_id = context.get("team_id")
                matches = self.detect_skill_triggers(user_message, user_id, team_id)
                skills = [m.skill for m in matches[:max_skills]]
            else:
                skills = []

        if not skills:
            return base_prompt

        # Build skill injection section
        skill_sections = []
        for skill in skills:
            skill_content = skill.render_prompt(context)
            skill_sections.append(
                f"""
## Skill: {skill.name}
{skill.description}

{skill_content}
"""
            )

        # Inject skills into prompt
        skills_text = "\n---\n".join(skill_sections)

        enhanced_prompt = f"""{base_prompt}

# Active Skills

The following specialized skills have been activated for this request:

{skills_text}

---

Use the skill instructions above to guide your response."""

        logger.debug(f"Injected {len(skills)} skills into prompt")
        return enhanced_prompt

    def get_skill_for_action(self, action_type: str) -> Skill | None:
        """
        Get the skill associated with a specific action type.

        Args:
            action_type: Action type (e.g., 'RUN_BAS_REVIEW')

        Returns:
            Associated Skill or None
        """
        # Map actions to skills
        action_skill_map = {
            "RUN_BAS_REVIEW": "bas_review",
            "REVIEW_TRANSACTIONS": "transaction_review",
            "CLASSIFY_GST": "gst_classification",
            "GENERATE_JOURNALS": "journal_generation",
        }

        skill_name = action_skill_map.get(action_type)
        if skill_name:
            return self.registry.get_skill(skill_name)

        return None

    def build_prompt_for_action(
        self,
        action_type: str,
        base_prompt: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """
        Build a prompt for a specific action, injecting the appropriate skill.

        Args:
            action_type: The action being performed
            base_prompt: Base prompt to enhance
            context: Optional context for skill rendering

        Returns:
            Enhanced prompt with action-specific skill
        """
        skill = self.get_skill_for_action(action_type)
        if skill:
            return self.inject_skills(base_prompt, context, skills=[skill])
        return base_prompt


# Module-level singleton
_default_injector: SkillInjector | None = None


def get_injector() -> SkillInjector:
    """Get or create the default skill injector singleton."""
    global _default_injector
    if _default_injector is None:
        _default_injector = SkillInjector()
    return _default_injector
