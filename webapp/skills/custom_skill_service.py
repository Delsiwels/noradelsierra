"""
Custom Skill Service

CRUD operations for user-defined and team-shared skills.
Handles R2 storage, database sync, and validation.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

from . import SkillLoader
from .r2_skill_loader import (
    R2SkillLoader,
    R2SkillLoaderError,
    R2StorageDisabledError,
    get_r2_loader,
)
from .skill_registry import get_registry

if TYPE_CHECKING:
    from webapp.models import CustomSkill

logger = logging.getLogger(__name__)


class CustomSkillServiceError(Exception):
    """Base exception for custom skill service errors."""

    pass


class ValidationError(CustomSkillServiceError):
    """Raised when skill content validation fails."""

    pass


class DuplicateSkillError(CustomSkillServiceError):
    """Raised when a skill with the same name already exists."""

    pass


class SkillNotFoundError(CustomSkillServiceError):
    """Raised when a skill is not found."""

    pass


class PermissionDeniedError(CustomSkillServiceError):
    """Raised when user lacks permission for an operation."""

    pass


class CustomSkillService:
    """
    Service for managing custom skills.

    Provides CRUD operations with automatic R2 sync and database updates.

    Usage:
        service = CustomSkillService()

        # Create a new skill
        skill = service.create_skill(
            content=skill_content,
            scope='private',
            user_id=current_user.id,
            created_by=current_user.id
        )

        # Update a skill
        service.update_skill(skill.id, new_content, user_id=current_user.id)

        # Delete a skill
        service.delete_skill(skill.id, user_id=current_user.id)

        # Promote to team
        service.promote_to_shared(skill.id, team_id, user_id=current_user.id)
    """

    def __init__(self, r2_loader: R2SkillLoader | None = None):
        """
        Initialize the custom skill service.

        Args:
            r2_loader: Optional R2 loader instance. Uses default if not provided.
        """
        self.r2_loader = r2_loader
        self.skill_loader = SkillLoader()

    def _get_r2_loader(self) -> R2SkillLoader:
        """Get R2 loader, using singleton if not injected."""
        if self.r2_loader:
            return self.r2_loader
        return get_r2_loader()

    def validate_skill_content(
        self, content: str
    ) -> tuple[bool, str | None, dict | None]:
        """
        Validate SKILL.md content format and extract metadata.

        Args:
            content: SKILL.md content to validate

        Returns:
            Tuple of (is_valid, error_message, metadata_dict)
        """
        is_valid, error = self.skill_loader.validate_content(content)
        if not is_valid:
            return False, error, None

        # Parse to extract metadata
        skill = self.skill_loader.load_from_content(content, path="validation")
        if not skill:
            return False, "Failed to parse skill content", None

        metadata = {
            "name": skill.name,
            "description": skill.description,
            "version": skill.metadata.version,
            "author": skill.metadata.author,
            "triggers": skill.triggers,
            "industries": skill.industries,
            "tags": skill.metadata.tags,
        }

        return True, None, metadata

    def _compute_content_hash(self, content: str) -> str:
        """Compute SHA-256 hash of content for cache invalidation."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def create_skill(
        self,
        content: str,
        scope: str,
        user_id: str | None = None,
        team_id: str | None = None,
        created_by: str = "",
    ) -> CustomSkill:
        """
        Create a new custom skill.

        Args:
            content: SKILL.md content
            scope: 'private' or 'shared'
            user_id: User ID (required for private skills)
            team_id: Team ID (required for shared skills)
            created_by: ID of user creating the skill

        Returns:
            Created CustomSkill instance

        Raises:
            ValidationError: If content is invalid
            DuplicateSkillError: If skill name already exists for this scope
            CustomSkillServiceError: If creation fails
        """
        # Validate scope and ownership
        if scope == "private":
            if not user_id:
                raise ValidationError("user_id required for private skills")
            owner_id = user_id
        elif scope == "shared":
            if not team_id:
                raise ValidationError("team_id required for shared skills")
            owner_id = team_id
        else:
            raise ValidationError(f"Invalid scope: {scope}")

        # Validate content
        is_valid, error, metadata = self.validate_skill_content(content)
        if not is_valid:
            raise ValidationError(error or "Invalid skill content")

        if not metadata:
            raise ValidationError("Failed to extract metadata from content")

        skill_name = metadata["name"]

        # Import models
        from webapp.models import CustomSkill, db

        # Check for duplicate
        query = CustomSkill.query.filter_by(name=skill_name, is_active=True)
        if scope == "private":
            query = query.filter_by(user_id=user_id)
        else:
            query = query.filter_by(team_id=team_id)

        if query.first():
            raise DuplicateSkillError(f"Skill '{skill_name}' already exists")

        # Generate storage key
        storage_key = R2SkillLoader.generate_storage_key(scope, owner_id, skill_name)

        # Upload to R2 (if enabled)
        try:
            r2_loader = self._get_r2_loader()
            if r2_loader.is_enabled:
                r2_loader.upload(storage_key, content)
        except R2StorageDisabledError:
            logger.info("R2 storage disabled - skill will be created without R2 backup")
        except R2SkillLoaderError as e:
            raise CustomSkillServiceError(f"Failed to upload to R2: {e}") from e

        # Create database record
        custom_skill = CustomSkill(
            user_id=user_id if scope == "private" else None,
            team_id=team_id if scope == "shared" else None,
            created_by=created_by,
            name=skill_name,
            description=metadata.get("description", ""),
            version=metadata.get("version", "1.0.0"),
            author=metadata.get("author", ""),
            triggers=metadata.get("triggers", []),
            industries=metadata.get("industries", []),
            tags=metadata.get("tags", []),
            storage_key=storage_key,
            scope=scope,
            is_active=True,
            content_hash=self._compute_content_hash(content),
        )

        db.session.add(custom_skill)
        db.session.commit()

        # Invalidate registry cache
        get_registry().invalidate_r2_cache(storage_key)

        logger.info(f"Created custom skill: {skill_name} ({scope})")
        return custom_skill

    def update_skill(
        self,
        skill_id: str,
        content: str,
        user_id: str | None = None,
    ) -> CustomSkill:
        """
        Update an existing custom skill.

        Args:
            skill_id: ID of the skill to update
            content: New SKILL.md content
            user_id: ID of user performing the update (for permission check)

        Returns:
            Updated CustomSkill instance

        Raises:
            SkillNotFoundError: If skill not found
            PermissionDeniedError: If user lacks permission
            ValidationError: If content is invalid
            CustomSkillServiceError: If update fails
        """
        from webapp.models import CustomSkill, db

        custom_skill: CustomSkill | None = CustomSkill.query.get(skill_id)
        if not custom_skill or not custom_skill.is_active:
            raise SkillNotFoundError(f"Skill {skill_id} not found")

        # Permission check
        if custom_skill.scope == "private" and custom_skill.user_id != user_id:
            raise PermissionDeniedError("Cannot update another user's private skill")

        # Validate content
        is_valid, error, metadata = self.validate_skill_content(content)
        if not is_valid:
            raise ValidationError(error or "Invalid skill content")

        if not metadata:
            raise ValidationError("Failed to extract metadata from content")

        # Check if name changed (not allowed)
        new_name = metadata["name"]
        if new_name != custom_skill.name:
            raise ValidationError(
                "Cannot change skill name. Create a new skill instead."
            )

        # Compute new content hash
        new_hash = self._compute_content_hash(content)

        # Skip if content unchanged
        if new_hash == custom_skill.content_hash:
            logger.debug(f"Skill {skill_id} content unchanged, skipping update")
            return custom_skill

        # Upload to R2 (if enabled)
        try:
            r2_loader = self._get_r2_loader()
            if r2_loader.is_enabled:
                r2_loader.upload(custom_skill.storage_key, content)
        except R2StorageDisabledError:
            logger.info("R2 storage disabled - skill updated in database only")
        except R2SkillLoaderError as e:
            raise CustomSkillServiceError(f"Failed to upload to R2: {e}") from e

        # Update database record
        custom_skill.description = metadata.get("description", "")
        custom_skill.version = metadata.get("version", "1.0.0")
        custom_skill.author = metadata.get("author", "")
        custom_skill.triggers = metadata.get("triggers", [])
        custom_skill.industries = metadata.get("industries", [])
        custom_skill.tags = metadata.get("tags", [])
        custom_skill.content_hash = new_hash

        db.session.commit()

        # Invalidate registry cache
        get_registry().invalidate_r2_cache(custom_skill.storage_key)

        logger.info(f"Updated custom skill: {custom_skill.name}")
        return custom_skill

    def delete_skill(
        self,
        skill_id: str,
        user_id: str | None = None,
    ) -> bool:
        """
        Delete a custom skill.

        Args:
            skill_id: ID of the skill to delete
            user_id: ID of user performing the delete (for permission check)

        Returns:
            True if deleted successfully

        Raises:
            SkillNotFoundError: If skill not found
            PermissionDeniedError: If user lacks permission
            CustomSkillServiceError: If delete fails
        """
        from webapp.models import CustomSkill, db

        custom_skill = CustomSkill.query.get(skill_id)
        if not custom_skill:
            raise SkillNotFoundError(f"Skill {skill_id} not found")

        # Permission check
        if custom_skill.scope == "private" and custom_skill.user_id != user_id:
            raise PermissionDeniedError("Cannot delete another user's private skill")

        storage_key = custom_skill.storage_key

        # Delete from R2 (if enabled)
        try:
            r2_loader = self._get_r2_loader()
            if r2_loader.is_enabled:
                r2_loader.delete(storage_key)
        except R2StorageDisabledError:
            logger.info("R2 storage disabled - skill deleted from database only")
        except R2SkillLoaderError as e:
            logger.warning("Failed to delete from R2 (continuing): %s", e)  # noqa: S608

        # Delete database record
        db.session.delete(custom_skill)
        db.session.commit()

        # Invalidate registry cache
        get_registry().invalidate_r2_cache(storage_key)

        logger.info(f"Deleted custom skill: {custom_skill.name}")
        return True

    def promote_to_shared(
        self,
        skill_id: str,
        team_id: str,
        user_id: str,
    ) -> CustomSkill:
        """
        Promote a private skill to team-shared.

        This creates a copy of the skill in the team's namespace.
        The original private skill is kept.

        Args:
            skill_id: ID of the private skill to promote
            team_id: Team ID to share with
            user_id: ID of user performing the operation

        Returns:
            New shared CustomSkill instance

        Raises:
            SkillNotFoundError: If skill not found
            PermissionDeniedError: If user lacks permission
            DuplicateSkillError: If skill name already exists in team
            CustomSkillServiceError: If promotion fails
        """
        from webapp.models import CustomSkill

        # Get the private skill
        private_skill = CustomSkill.query.get(skill_id)
        if not private_skill:
            raise SkillNotFoundError(f"Skill {skill_id} not found")

        # Permission check - only owner can promote
        if private_skill.user_id != user_id:
            raise PermissionDeniedError("Cannot promote another user's skill")

        if private_skill.scope != "private":
            raise ValidationError("Only private skills can be promoted to shared")

        # Check for duplicate in team
        existing = CustomSkill.query.filter_by(
            name=private_skill.name, team_id=team_id, is_active=True
        ).first()
        if existing:
            raise DuplicateSkillError(
                f"Skill '{private_skill.name}' already exists in team"
            )

        # Download content from R2
        content = None
        try:
            r2_loader = self._get_r2_loader()
            if r2_loader.is_enabled:
                content = r2_loader.download(private_skill.storage_key)
        except (R2StorageDisabledError, R2SkillLoaderError) as e:
            logger.warning(f"Could not load skill content from R2: {e}")

        if not content:
            # Create minimal content from metadata
            content = f"""---
name: {private_skill.name}
description: {private_skill.description or ''}
version: {private_skill.version or '1.0.0'}
author: {private_skill.author or ''}
triggers: {private_skill.triggers or []}
industries: {private_skill.industries or []}
tags: {private_skill.tags or []}
---

# {private_skill.name}

{private_skill.description or 'No content available'}
"""

        # Create the shared skill
        shared_skill = self.create_skill(
            content=content,
            scope="shared",
            team_id=team_id,
            created_by=user_id,
        )

        logger.info(f"Promoted skill '{private_skill.name}' to team {team_id}")
        return shared_skill

    def get_skill(self, skill_id: str) -> CustomSkill | None:
        """
        Get a custom skill by ID.

        Args:
            skill_id: Skill ID

        Returns:
            CustomSkill instance or None if not found
        """
        from webapp.models import CustomSkill

        result: CustomSkill | None = CustomSkill.query.get(skill_id)
        return result

    def get_skill_content(self, skill_id: str) -> str | None:
        """
        Get full skill content from R2.

        Args:
            skill_id: Skill ID

        Returns:
            SKILL.md content or None if not found
        """
        from webapp.models import CustomSkill

        custom_skill = CustomSkill.query.get(skill_id)
        if not custom_skill:
            return None

        try:
            r2_loader = self._get_r2_loader()
            if r2_loader.is_enabled:
                return r2_loader.download(custom_skill.storage_key)
        except (R2StorageDisabledError, R2SkillLoaderError) as e:
            logger.warning(f"Could not load skill content from R2: {e}")

        return None

    def list_user_skills(self, user_id: str) -> list[CustomSkill]:
        """
        List all private skills for a user.

        Args:
            user_id: User ID

        Returns:
            List of CustomSkill instances
        """
        from webapp.models import CustomSkill

        result: list[CustomSkill] = CustomSkill.query.filter_by(
            user_id=user_id, scope="private", is_active=True
        ).all()
        return result

    def list_team_skills(self, team_id: str) -> list[CustomSkill]:
        """
        List all shared skills for a team.

        Args:
            team_id: Team ID

        Returns:
            List of CustomSkill instances
        """
        from webapp.models import CustomSkill

        result: list[CustomSkill] = CustomSkill.query.filter_by(
            team_id=team_id, scope="shared", is_active=True
        ).all()
        return result


# Module-level singleton
_service: CustomSkillService | None = None


def get_custom_skill_service() -> CustomSkillService:
    """Get the custom skill service singleton."""
    global _service
    if _service is None:
        _service = CustomSkillService()
    return _service
