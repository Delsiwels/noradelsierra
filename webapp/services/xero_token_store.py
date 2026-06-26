"""Server-side encrypted storage for Xero connection tokens (audit #3).

When TOKEN_ENCRYPTION_KEY is configured, a logged-in user's Xero connection is
stored here (Fernet-encrypted) instead of in the client-side session cookie.
Every function degrades gracefully — returns False/None / no-ops — when
encryption is unavailable or no user_id is supplied, so callers can fall back
to session storage during migration.
"""

from __future__ import annotations

import json
import logging

from webapp.services import crypto

logger = logging.getLogger(__name__)


def is_available() -> bool:
    """True when server-side encrypted token storage can be used."""
    return crypto.encryption_available()


def save_connection(user_id: str | None, connection: dict) -> bool:
    """Encrypt and persist a user's Xero connection. Returns False if unavailable."""
    if not user_id or not crypto.encryption_available():
        return False
    blob = crypto.encrypt(json.dumps(connection))
    if blob is None:
        return False

    from webapp.models import XeroToken, db

    row = XeroToken.query.filter_by(user_id=user_id).first()
    if row is None:
        db.session.add(XeroToken(user_id=user_id, encrypted_data=blob))
    else:
        row.encrypted_data = blob
    db.session.commit()
    return True


def load_connection(user_id: str | None) -> dict | None:
    """Load and decrypt a user's stored Xero connection, or None."""
    if not user_id or not crypto.encryption_available():
        return None

    from webapp.models import XeroToken

    row = XeroToken.query.filter_by(user_id=user_id).first()
    if row is None:
        return None
    plaintext = crypto.decrypt(row.encrypted_data)
    if plaintext is None:
        return None
    try:
        data = json.loads(plaintext)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def clear_connection(user_id: str | None) -> None:
    """Delete a user's stored Xero connection, if any."""
    if not user_id:
        return
    from webapp.models import XeroToken, db

    XeroToken.query.filter_by(user_id=user_id).delete()
    db.session.commit()
