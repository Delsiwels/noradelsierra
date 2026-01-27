"""Database models for Custom Skills Infrastructure."""

import uuid
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def generate_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid.uuid4())


class CustomSkill(db.Model):  # type: ignore[name-defined]
    """
    Custom skill model for user-defined and team-shared skills.

    Skills are stored in R2 with metadata synced to the database for fast queries.
    Supports both private (user-owned) and shared (team-owned) scopes.
    """

    __tablename__ = "custom_skills"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)

    # Ownership (one of user_id or team_id must be set)
    user_id = db.Column(db.String(36), nullable=True, index=True)
    team_id = db.Column(db.String(36), nullable=True, index=True)
    created_by = db.Column(db.String(36), nullable=False)

    # Metadata (synced from SKILL.md frontmatter)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    version = db.Column(db.String(20), default="1.0.0")
    author = db.Column(db.String(255))
    triggers = db.Column(db.JSON, default=list)
    industries = db.Column(db.JSON, default=list)
    tags = db.Column(db.JSON, default=list)

    # R2 reference
    storage_key = db.Column(db.String(255), nullable=False, unique=True, index=True)
    scope = db.Column(
        db.String(20), nullable=False, default="private"
    )  # 'private' or 'shared'

    # Status
    is_active = db.Column(db.Boolean, default=True)
    content_hash = db.Column(
        db.String(64)
    )  # SHA-256 hash of content for cache invalidation

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Constraints
    __table_args__ = (
        db.UniqueConstraint("user_id", "name", name="uq_user_skill_name"),
        db.UniqueConstraint("team_id", "name", name="uq_team_skill_name"),
        db.CheckConstraint(
            "(user_id IS NOT NULL AND team_id IS NULL) OR (user_id IS NULL AND team_id IS NOT NULL)",
            name="ck_skill_ownership",
        ),
    )

    def to_dict(self, include_content: bool = False) -> dict:
        """
        Convert skill to dictionary for API responses.

        Args:
            include_content: Whether to include full content (requires R2 fetch)

        Returns:
            Dictionary representation of the skill
        """
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "triggers": self.triggers or [],
            "industries": self.industries or [],
            "tags": self.tags or [],
            "scope": self.scope,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "user_id": self.user_id,
            "team_id": self.team_id,
            "created_by": self.created_by,
        }

    @property
    def is_private(self) -> bool:
        """Check if skill is private (user-owned)."""
        return self.scope == "private" and self.user_id is not None

    @property
    def is_shared(self) -> bool:
        """Check if skill is shared (team-owned)."""
        return self.scope == "shared" and self.team_id is not None

    def __repr__(self) -> str:
        return f"<CustomSkill {self.name} ({self.scope})>"
