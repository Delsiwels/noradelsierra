"""Database models for Custom Skills Infrastructure."""

import uuid
from datetime import datetime, timedelta

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def generate_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid.uuid4())


def default_expires_at() -> datetime:
    """Generate default expiration date (30 days from now)."""
    return datetime.utcnow() + timedelta(days=30)


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


class Conversation(db.Model):  # type: ignore[name-defined]
    """
    Conversation model for storing chat history.

    Conversations have a 30-day retention period by default.
    """

    __tablename__ = "conversations"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), nullable=False, index=True)
    title = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    expires_at = db.Column(db.DateTime, default=default_expires_at, index=True)

    # Relationship to messages
    messages = db.relationship(
        "Message", backref="conversation", cascade="all, delete-orphan", lazy="dynamic"
    )

    def to_dict(self, include_messages: bool = False) -> dict:
        """Convert conversation to dictionary."""
        data: dict = {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "message_count": self.messages.count() if self.messages else 0,
        }
        if include_messages:
            data["messages"] = [m.to_dict() for m in self.messages.order_by(Message.created_at)]  # type: ignore[misc,operator]
        return data

    def __repr__(self) -> str:
        return f"<Conversation {self.id[:8]}... ({self.user_id})>"


class Message(db.Model):  # type: ignore[name-defined]
    """
    Message model for storing individual chat messages within a conversation.
    """

    __tablename__ = "messages"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    conversation_id = db.Column(
        db.String(36), db.ForeignKey("conversations.id"), nullable=False, index=True
    )
    role = db.Column(db.String(20), nullable=False)  # 'user' or 'assistant'
    content = db.Column(db.Text, nullable=False)
    model = db.Column(db.String(100))
    skills_used = db.Column(db.JSON, default=list)
    input_tokens = db.Column(db.Integer, default=0)
    output_tokens = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "model": self.model,
            "skills_used": self.skills_used or [],
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<Message {self.id[:8]}... ({self.role})>"


class SkillUsage(db.Model):  # type: ignore[name-defined]
    """
    Skill usage tracking for analytics.
    """

    __tablename__ = "skill_usages"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    skill_name = db.Column(db.String(100), nullable=False, index=True)
    skill_source = db.Column(db.String(20), nullable=False)  # 'public', 'private', 'shared'
    user_id = db.Column(db.String(36), index=True)
    team_id = db.Column(db.String(36), index=True)
    trigger = db.Column(db.String(255))
    confidence = db.Column(db.Float)
    conversation_id = db.Column(db.String(36))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        """Convert skill usage to dictionary."""
        return {
            "id": self.id,
            "skill_name": self.skill_name,
            "skill_source": self.skill_source,
            "user_id": self.user_id,
            "team_id": self.team_id,
            "trigger": self.trigger,
            "confidence": self.confidence,
            "conversation_id": self.conversation_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<SkillUsage {self.skill_name} ({self.skill_source})>"


class TokenUsage(db.Model):  # type: ignore[name-defined]
    """
    Token usage tracking per user/team per month.
    """

    __tablename__ = "token_usages"

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), index=True)
    team_id = db.Column(db.String(36), index=True)
    period_year = db.Column(db.Integer, nullable=False)
    period_month = db.Column(db.Integer, nullable=False)
    input_tokens = db.Column(db.BigInteger, default=0)
    output_tokens = db.Column(db.BigInteger, default=0)
    total_tokens = db.Column(db.BigInteger, default=0)
    request_count = db.Column(db.Integer, default=0)
    monthly_limit = db.Column(db.BigInteger)  # Null = use default from config

    # Unique constraint for one record per user/team per period
    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "team_id", "period_year", "period_month",
            name="uq_token_usage_period"
        ),
    )

    def to_dict(self) -> dict:
        """Convert token usage to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "team_id": self.team_id,
            "period_year": self.period_year,
            "period_month": self.period_month,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "request_count": self.request_count,
            "monthly_limit": self.monthly_limit,
        }

    def __repr__(self) -> str:
        return f"<TokenUsage {self.period_year}-{self.period_month:02d} ({self.total_tokens} tokens)>"
