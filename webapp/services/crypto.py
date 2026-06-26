"""Symmetric encryption for sensitive at-rest secrets (e.g. Xero tokens).

Uses Fernet (AES-128-CBC + HMAC) with a key from ``TOKEN_ENCRYPTION_KEY``. When
the key is absent, encryption is unavailable and callers fall back to their
prior behaviour — so a deploy without the key provisioned never breaks, it
simply doesn't yet gain at-rest encryption.
"""

from __future__ import annotations

import base64
import hashlib
import logging

from flask import current_app

logger = logging.getLogger(__name__)


def _load_fernet():
    """Return a Fernet instance from TOKEN_ENCRYPTION_KEY, or None if unavailable."""
    key = current_app.config.get("TOKEN_ENCRYPTION_KEY")
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
    except ImportError:  # pragma: no cover - dependency is declared
        logger.warning("cryptography not installed; token encryption disabled")
        return None

    key_bytes = key.encode() if isinstance(key, str) else key
    try:
        # Accept a real urlsafe-base64 Fernet key directly; otherwise derive a
        # valid 32-byte key from an arbitrary secret via SHA-256.
        try:
            return Fernet(key_bytes)
        except (ValueError, TypeError):
            derived = base64.urlsafe_b64encode(hashlib.sha256(key_bytes).digest())
            return Fernet(derived)
    except Exception:
        logger.exception("Failed to initialise token encryption")
        return None


def encryption_available() -> bool:
    """True when a usable TOKEN_ENCRYPTION_KEY is configured."""
    return _load_fernet() is not None


def encrypt(plaintext: str | None) -> str | None:
    """Encrypt a string, or return None if encryption is unavailable/empty input."""
    fernet = _load_fernet()
    if fernet is None or not plaintext:
        return None
    return str(fernet.encrypt(plaintext.encode()).decode())


def decrypt(token: str | None) -> str | None:
    """Decrypt a token, or return None if unavailable/invalid (e.g. rotated key)."""
    fernet = _load_fernet()
    if fernet is None or not token:
        return None
    try:
        return str(fernet.decrypt(token.encode()).decode())
    except Exception:
        logger.warning("Failed to decrypt token (key rotated or value corrupt)")
        return None
