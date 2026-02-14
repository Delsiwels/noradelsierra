"""
Skill Registry

Discovers and caches skills from multiple sources:
- Public skills (filesystem)
- Private skills (R2 + database, user-owned)
- Shared skills (R2 + database, team-owned)

Priority resolution: private > shared > public
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from . import SkillLoader
from .models import Skill, SkillMetadata

if TYPE_CHECKING:
    from webapp.models import CustomSkill

logger = logging.getLogger(__name__)

# Cache TTL for R2-loaded skills (5 minutes)
R2_CACHE_TTL = 300


class SkillRegistry:
    """
    Discovers and caches skill metadata from multiple sources.

    Skills are loaded lazily - metadata is discovered on startup, but full
    skill content is only loaded when requested. R2-loaded skills are cached
    with a 5-minute TTL.

    Usage:
        registry = SkillRegistry()
        skills = registry.discover_skills()
        skill = registry.get_skill('bas_review')

        # Multi-source with priority
        skill = registry.get_skill_with_priority('my_skill', user_id, team_id)
        all_skills = registry.discover_all_skills(user_id, team_id)
    """

    def __init__(self, skills_dir: str | Path | None = None):
        """
        Initialize the skill registry.

        Args:
            skills_dir: Path to public skills directory. Defaults to webapp/skills/public/
        """
        if skills_dir is None:
            # Default to webapp/skills/public/
            base_dir = Path(__file__).parent
            self.skills_dir = base_dir / "public"
        else:
            self.skills_dir = Path(skills_dir)
        self.loader = SkillLoader()
        self._skill_cache: dict[str, Skill] = {}
        self._metadata_cache: dict[str, SkillMetadata] = {}
        self._discovered = False

        # R2 cache with TTL
        self._r2_cache: dict[str, tuple[Skill, float]] = {}  # key -> (skill, timestamp)

    def discover_skills(self) -> list[SkillMetadata]:
        """
        Find all available public skills in the skills directory.

        Returns:
            List of SkillMetadata for all discovered public skills
        """
        if self._discovered:
            return list(self._metadata_cache.values())

        if not self.skills_dir.exists():
            logger.warning(f"Skills directory not found: {self.skills_dir}")
            return []

        metadata_list = []

        # Look for SKILL.md files in subdirectories
        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            skill = self.loader.load_from_path(str(skill_file))
            if skill:
                skill.source = "public"
                self._skill_cache[skill.name] = skill
                self._metadata_cache[skill.name] = skill.metadata
                metadata_list.append(skill.metadata)
                logger.debug(f"Discovered public skill: {skill.name}")

        self._discovered = True
        logger.info(f"Discovered {len(metadata_list)} public skills")

        return metadata_list

    def get_skill(self, skill_name: str) -> Skill | None:
        """
        Load full public skill content by name (lazy loading with caching).

        Args:
            skill_name: Name of the skill to load

        Returns:
            Skill object or None if not found
        """
        # Ensure skills are discovered
        if not self._discovered:
            self.discover_skills()

        # Return from cache if available
        if skill_name in self._skill_cache:
            return self._skill_cache[skill_name]

        # Try to load from filesystem
        skill_path = self.skills_dir / skill_name / "SKILL.md"
        if skill_path.exists():
            skill = self.loader.load_from_path(str(skill_path))
            if skill:
                skill.source = "public"
                self._skill_cache[skill_name] = skill
                self._metadata_cache[skill_name] = skill.metadata
                return skill

        return None

    def get_skill_with_priority(
        self,
        skill_name: str,
        user_id: str | None = None,
        team_id: str | None = None,
    ) -> Skill | None:
        """
        Get skill with priority resolution: private > shared > public.

        Args:
            skill_name: Name of the skill
            user_id: Current user's ID (for private skill lookup)
            team_id: Current user's team ID (for shared skill lookup)

        Returns:
            Skill with highest priority, or None if not found
        """
        # 1. Check private skills first
        if user_id:
            private_skill = self._get_custom_skill(skill_name, user_id=user_id)
            if private_skill:
                return private_skill

        # 2. Check shared skills
        if team_id:
            shared_skill = self._get_custom_skill(skill_name, team_id=team_id)
            if shared_skill:
                return shared_skill

        # 3. Fall back to public skills
        return self.get_skill(skill_name)

    def _get_custom_skill(
        self,
        skill_name: str,
        user_id: str | None = None,
        team_id: str | None = None,
    ) -> Skill | None:
        """
        Get a custom skill from database + R2.

        Args:
            skill_name: Name of the skill
            user_id: User ID for private skills
            team_id: Team ID for shared skills

        Returns:
            Skill object or None if not found
        """
        # Import here to avoid circular imports
        try:
            from webapp.models import CustomSkill
            from webapp.skills.r2_skill_loader import (
                R2StorageDisabledError,
                get_r2_loader,
            )
        except ImportError:
            logger.warning("Could not import CustomSkill model or R2 loader")
            return None

        # Build query
        query = CustomSkill.query.filter_by(name=skill_name, is_active=True)
        if user_id:
            query = query.filter_by(user_id=user_id, scope="private")
        elif team_id:
            query = query.filter_by(team_id=team_id, scope="shared")
        else:
            return None

        custom_skill = query.first()
        if not custom_skill:
            return None

        # Check R2 cache
        cache_key = custom_skill.storage_key
        if cache_key in self._r2_cache:
            skill, timestamp = self._r2_cache[cache_key]
            if time.time() - timestamp < R2_CACHE_TTL:
                # Check content hash for cache invalidation
                if skill.metadata.version == custom_skill.version:
                    return skill

        # Load from R2
        try:
            r2_loader = get_r2_loader()
            content = r2_loader.download(custom_skill.storage_key)
            if not content:
                logger.warning(
                    f"Custom skill not found in R2: {custom_skill.storage_key}"
                )
                return None

            source = "private" if user_id else "shared"
            owner_id = user_id or team_id

            loaded_skill = self.loader.load_from_content(
                content,
                path=f"r2://{custom_skill.storage_key}",
                source=source,
                owner_id=owner_id,
            )

            if loaded_skill:
                # Update R2 cache
                self._r2_cache[cache_key] = (loaded_skill, time.time())

            return loaded_skill

        except R2StorageDisabledError:
            logger.debug("R2 storage disabled, skipping custom skill lookup")
            return None
        except Exception as e:
            logger.error(f"Error loading custom skill from R2: {e}")
            return None

    def discover_all_skills(
        self,
        user_id: str | None = None,
        team_id: str | None = None,
    ) -> dict[str, list[Skill]]:
        """
        Discover all skills from all sources.

        Returns skills grouped by source, allowing UI to display them separately.

        Args:
            user_id: Current user's ID (for private skills)
            team_id: Current user's team ID (for shared skills)

        Returns:
            Dict with keys 'private', 'shared', 'public' containing lists of skills
        """
        result: dict[str, list[Skill]] = {
            "private": [],
            "shared": [],
            "public": [],
        }

        # 1. Discover public skills
        self.discover_skills()
        result["public"] = list(self._skill_cache.values())

        # 2. Discover custom skills from database
        try:
            from webapp.models import CustomSkill
        except ImportError:
            logger.warning("Could not import CustomSkill model")
            return result

        # Private skills for this user
        if user_id:
            private_skills = CustomSkill.query.filter_by(
                user_id=user_id, scope="private", is_active=True
            ).all()
            for cs in private_skills:
                skill = self._load_custom_skill(cs, "private", user_id)
                if skill:
                    result["private"].append(skill)

        # Shared skills for this team
        if team_id:
            shared_skills = CustomSkill.query.filter_by(
                team_id=team_id, scope="shared", is_active=True
            ).all()
            for cs in shared_skills:
                skill = self._load_custom_skill(cs, "shared", team_id)
                if skill:
                    result["shared"].append(skill)

        return result

    def _load_custom_skill(
        self,
        custom_skill: CustomSkill,
        source: str,
        owner_id: str,
    ) -> Skill | None:
        """
        Load a custom skill from R2 with caching.

        Args:
            custom_skill: CustomSkill database record
            source: 'private' or 'shared'
            owner_id: user_id or team_id

        Returns:
            Skill object or None if loading fails
        """
        # Check R2 cache first
        cache_key = custom_skill.storage_key
        if cache_key in self._r2_cache:
            skill, timestamp = self._r2_cache[cache_key]
            if time.time() - timestamp < R2_CACHE_TTL:
                return skill

        try:
            from webapp.skills.r2_skill_loader import get_r2_loader

            r2_loader = get_r2_loader()
            content = r2_loader.download(custom_skill.storage_key)
            if not content:
                # R2 content missing - create a minimal skill from DB metadata
                return self._skill_from_metadata(custom_skill, source, owner_id)

            loaded_skill = self.loader.load_from_content(
                content,
                path=f"r2://{custom_skill.storage_key}",
                source=source,
                owner_id=owner_id,
            )

            if loaded_skill:
                self._r2_cache[cache_key] = (loaded_skill, time.time())
                return loaded_skill

        except Exception as e:
            logger.error(f"Error loading custom skill from R2: {e}")
            # Fall back to metadata-only skill
            return self._skill_from_metadata(custom_skill, source, owner_id)

        return None

    def _skill_from_metadata(
        self,
        custom_skill: CustomSkill,
        source: str,
        owner_id: str,
    ) -> Skill:
        """
        Create a minimal Skill from database metadata when R2 is unavailable.

        Args:
            custom_skill: CustomSkill database record
            source: 'private' or 'shared'
            owner_id: user_id or team_id

        Returns:
            Skill object with metadata but minimal content
        """
        metadata = SkillMetadata(
            name=custom_skill.name,
            description=custom_skill.description or "",
            version=custom_skill.version or "1.0.0",
            author=custom_skill.author or "",
            triggers=custom_skill.triggers or [],
            industries=custom_skill.industries or [],
            tags=custom_skill.tags or [],
        )

        return Skill(
            metadata=metadata,
            content=f"# {custom_skill.name}\n\n{custom_skill.description or 'No content available'}",
            path=f"db://{custom_skill.id}",
            source=source,
            owner_id=owner_id,
        )

    def get_skills_by_trigger(
        self,
        message: str,
        user_id: str | None = None,
        team_id: str | None = None,
    ) -> list[Skill]:
        """
        Find skills matching trigger patterns in message.

        Searches all sources with priority: private > shared > public.
        Returns unique skills by name (highest priority wins).

        Args:
            message: User message to match against triggers
            user_id: Current user's ID (for private skill lookup)
            team_id: Current user's team ID (for shared skill lookup)

        Returns:
            List of matching skills, sorted by relevance
        """
        message_lower = message.lower()
        matches: dict[str, Skill] = {}

        # Get all skills with priority ordering
        all_skills = self.discover_all_skills(user_id, team_id)

        # Check in priority order: private, shared, public
        for source in ["private", "shared", "public"]:
            for skill in all_skills[source]:
                # Skip if already matched by higher priority source
                if skill.name in matches:
                    continue

                for trigger in skill.triggers:
                    trigger_lower = trigger.lower()
                    if trigger_lower in message_lower:
                        matches[skill.name] = skill
                        break

        return list(matches.values())

    def get_skills_by_industry(
        self,
        industry: str,
        user_id: str | None = None,
        team_id: str | None = None,
    ) -> list[Skill]:
        """
        Find skills that support a specific industry.

        Args:
            industry: Industry name (e.g., 'hospitality')
            user_id: Current user's ID
            team_id: Current user's team ID

        Returns:
            List of skills supporting the industry
        """
        industry_lower = industry.lower()
        matches: dict[str, Skill] = {}

        all_skills = self.discover_all_skills(user_id, team_id)

        for source in ["private", "shared", "public"]:
            for skill in all_skills[source]:
                if skill.name in matches:
                    continue

                if industry_lower in [i.lower() for i in skill.industries]:
                    matches[skill.name] = skill

        return list(matches.values())

    def get_all_skills(self) -> list[Skill]:
        """
        Get all discovered public skills with full content.

        Returns:
            List of all public Skill objects
        """
        if not self._discovered:
            self.discover_skills()

        return list(self._skill_cache.values())

    def list_skill_names(self) -> list[str]:
        """
        Get list of all public skill names.

        Returns:
            List of skill names
        """
        if not self._discovered:
            self.discover_skills()

        return list(self._metadata_cache.keys())

    def reload(self) -> list[SkillMetadata]:
        """
        Reload all skills from filesystem.

        Returns:
            List of SkillMetadata after reload
        """
        self._skill_cache.clear()
        self._metadata_cache.clear()
        self._r2_cache.clear()
        self._discovered = False
        return self.discover_skills()

    def invalidate_r2_cache(self, storage_key: str | None = None) -> None:
        """
        Invalidate R2 cache.

        Args:
            storage_key: Specific key to invalidate, or None to clear all
        """
        if storage_key:
            self._r2_cache.pop(storage_key, None)
        else:
            self._r2_cache.clear()


# Module-level singleton for convenience
_default_registry: SkillRegistry | None = None


def get_registry() -> SkillRegistry:
    """Get or create the default skill registry singleton."""
    global _default_registry
    if _default_registry is None:
        _default_registry = SkillRegistry()
    return _default_registry
