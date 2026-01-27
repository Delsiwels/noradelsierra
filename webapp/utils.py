"""Utility functions."""

import hashlib
import re
from typing import Any


def validate_email(email: str) -> bool:
    """Validate email format."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def sanitize_input(text: str) -> str:
    """Sanitize user input to prevent XSS."""
    if not isinstance(text, str):
        return ""
    # Remove potentially dangerous characters
    sanitized = text.replace("<", "&lt;").replace(">", "&gt;")
    sanitized = sanitized.replace("'", "&#39;").replace('"', "&quot;")
    return sanitized


def hash_password(password: str) -> str:
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def paginate(items: list[Any], page: int, per_page: int) -> dict:
    """Paginate a list of items."""
    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page

    return {
        "items": items[start:end],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page,
    }
