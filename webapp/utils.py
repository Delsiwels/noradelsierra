"""Utility functions."""

import re


def validate_email(email: str) -> bool:
    """Validate email format. Falsy/non-string input returns False."""
    if not email:
        return False
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
