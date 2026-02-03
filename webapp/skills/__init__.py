"""
Skills System

A markdown-based skills system that extracts domain expertise from hardcoded
prompts into portable, editable markdown files. This enables users and teams
to create/edit skills without code changes.

Usage:
    from webapp.skills import SkillLoader, SkillRegistry, SkillInjector

    # Load a single skill from file
    loader = SkillLoader()
    skill = loader.load_from_path('/path/to/SKILL.md')

    # Load a skill from content string (for R2-loaded skills)
    skill = loader.load_from_content(content, path='r2://storage-key')

    # Discover all skills
    registry = SkillRegistry()
    skills = registry.discover_skills()

    # Inject skills into prompts
    injector = SkillInjector()
    enhanced_prompt = injector.inject_skills(base_prompt, user_message)
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from .models import Skill, SkillMetadata

logger = logging.getLogger(__name__)


class SkillLoader:
    """
    Parses SKILL.md files into structured Skill objects.

    SKILL.md files use YAML frontmatter for metadata followed by
    markdown content for the skill instructions.

    Example SKILL.md format:
        ---
        name: bas_review
        description: Reviews BAS compliance
        version: 1.0.0
        triggers:
          - "run bas review"
          - "check gst"
        ---

        # BAS Review Skill

        Instructions for the AI...
    """

    FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

    def load_from_path(self, path: str | Path) -> Skill | None:
        """
        Parse a SKILL.md file into a Skill object.

        Args:
            path: Path to the SKILL.md file

        Returns:
            Skill object or None if parsing fails
        """
        try:
            path_obj = Path(path) if isinstance(path, str) else path
            if not path_obj.exists():
                logger.warning(f"Skill file not found: {path_obj}")
                return None

            content = path_obj.read_text(encoding="utf-8")
            return self.load_from_content(content, str(path_obj))

        except Exception as e:
            logger.error(f"Error loading skill from {path}: {e}")
            return None

    def load_from_content(
        self,
        content: str,
        path: str = "memory",
        source: str = "public",
        owner_id: str | None = None,
    ) -> Skill | None:
        """
        Parse SKILL.md content string into a Skill object.

        This method is used for loading skills from R2 storage or other
        non-filesystem sources.

        Args:
            content: SKILL.md content string
            path: Path identifier (for logging and reference)
            source: Skill source ('public', 'private', 'shared')
            owner_id: Owner ID (user_id for private, team_id for shared)

        Returns:
            Skill object or None if parsing fails
        """
        try:
            metadata, body = self._parse_frontmatter(content)

            if metadata is None:
                logger.warning(f"Invalid frontmatter in skill: {path}")
                return None

            skill_metadata = self._build_metadata(metadata)

            skill = Skill(
                metadata=skill_metadata,
                content=body.strip(),
                path=path,
                source=source,
                owner_id=owner_id,
            )

            # Load guidelines if path is a real filesystem path with guidelines/
            if path != "memory" and not path.startswith("r2://"):
                path_obj = Path(path)
                if path_obj.exists():
                    skill_dir = path_obj.parent
                    guidelines_dir = skill_dir / "guidelines"
                    if guidelines_dir.exists():
                        skill.guidelines = self._load_guidelines(guidelines_dir)

            return skill

        except Exception as e:
            logger.error(f"Error loading skill from content ({path}): {e}")
            return None

    def _parse_frontmatter(self, content: str) -> tuple:
        """
        Extract YAML frontmatter and body from content.

        Returns:
            Tuple of (metadata_dict, body_content) or (None, content) if no frontmatter
        """
        match = self.FRONTMATTER_PATTERN.match(content)
        if not match:
            return None, content

        frontmatter_str = match.group(1)
        body = content[match.end() :]

        try:
            metadata = yaml.safe_load(frontmatter_str)
            return metadata, body
        except yaml.YAMLError as e:
            logger.error(f"YAML parse error in frontmatter: {e}")
            return None, content

    def _build_metadata(self, data: dict[str, Any]) -> SkillMetadata:
        """Build SkillMetadata from parsed YAML dict."""
        last_verified = data.get("last_verified")
        if isinstance(last_verified, str):
            try:
                last_verified = date.fromisoformat(last_verified)
            except ValueError:
                last_verified = None
        elif isinstance(last_verified, date):
            pass  # Already a date
        else:
            last_verified = None

        return SkillMetadata(
            name=data.get("name", "unnamed"),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            last_verified=last_verified,
            tax_agent_approved=data.get("tax_agent_approved", False),
            triggers=data.get("triggers", []),
            industries=data.get("industries", []),
            tags=data.get("tags", []),
        )

    def _load_guidelines(self, guidelines_dir: Path) -> dict[str, str]:
        """
        Load all industry guidelines from a guidelines directory.

        Args:
            guidelines_dir: Path to guidelines/ subdirectory

        Returns:
            Dict mapping industry name to guideline content
        """
        guidelines = {}

        for md_file in guidelines_dir.glob("*.md"):
            industry = md_file.stem  # e.g., 'hospitality' from 'hospitality.md'
            try:
                content = md_file.read_text(encoding="utf-8")
                guidelines[industry] = content
            except Exception as e:
                logger.warning(f"Failed to load guideline {md_file}: {e}")

        return guidelines

    def load_guidelines(self, skill: Skill, industry: str) -> str | None:
        """
        Load industry-specific guidelines for a skill.

        Args:
            skill: The skill to load guidelines for
            industry: Industry name (e.g., 'hospitality')

        Returns:
            Guideline content or None if not found
        """
        if industry in skill.guidelines:
            return skill.guidelines[industry]

        # Try loading from filesystem if not cached and path is valid
        if skill.path and skill.path != "memory" and not skill.path.startswith("r2://"):
            skill_dir = Path(skill.path).parent
            guideline_path = skill_dir / "guidelines" / f"{industry}.md"

            if guideline_path.exists():
                try:
                    content = guideline_path.read_text(encoding="utf-8")
                    skill.guidelines[industry] = content
                    return content
                except Exception as e:
                    logger.warning(f"Failed to load guideline {guideline_path}: {e}")

        return None

    def validate_content(self, content: str) -> tuple[bool, str | None]:
        """
        Validate SKILL.md content format.

        Args:
            content: SKILL.md content to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not content or not content.strip():
            return False, "Content is empty"

        # Check content size (100KB limit)
        if len(content.encode("utf-8")) > 100 * 1024:
            return False, "Content exceeds 100KB limit"

        # Check for frontmatter
        match = self.FRONTMATTER_PATTERN.match(content)
        if not match:
            return False, "Missing YAML frontmatter (must start with ---)"

        # Parse frontmatter
        frontmatter_str = match.group(1)
        try:
            metadata = yaml.safe_load(frontmatter_str)
        except yaml.YAMLError as e:
            return False, f"Invalid YAML frontmatter: {e}"

        if not isinstance(metadata, dict):
            return False, "Frontmatter must be a YAML dictionary"

        # Required fields
        if not metadata.get("name"):
            return False, "Missing required field: name"

        # Validate name format
        name = metadata.get("name", "")
        if not re.match(r"^[a-z][a-z0-9_]{0,99}$", name):
            return (
                False,
                "Invalid name format: must start with lowercase letter, "
                "contain only lowercase letters, numbers, and underscores, "
                "max 100 characters",
            )

        # Validate optional fields
        triggers = metadata.get("triggers", [])
        if not isinstance(triggers, list):
            return False, "triggers must be a list"

        industries = metadata.get("industries", [])
        if not isinstance(industries, list):
            return False, "industries must be a list"

        tags = metadata.get("tags", [])
        if not isinstance(tags, list):
            return False, "tags must be a list"

        return True, None


# Export public API (must be after SkillLoader class definition)
from .skill_injector import SkillInjector, get_injector  # noqa: E402
from .skill_registry import SkillRegistry, get_registry  # noqa: E402

__all__ = [
    "SkillLoader",
    "SkillRegistry",
    "get_registry",
    "SkillInjector",
    "get_injector",
    "Skill",
    "SkillMetadata",
    "SkillMatch",
]
