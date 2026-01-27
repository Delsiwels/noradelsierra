"""Data models."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class User:
    """User model."""

    id: int
    name: str
    email: str
    created_at: datetime | None = None

    def to_dict(self) -> dict:
        """Convert user to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class Item:
    """Item model."""

    id: int
    title: str
    description: str
    owner_id: int

    def to_dict(self) -> dict:
        """Convert item to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "owner_id": self.owner_id,
        }
