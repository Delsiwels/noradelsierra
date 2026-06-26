"""Shared Flask extension singletons (app-factory pattern).

Instantiated unbound at import time and bound to the application in
``webapp.app.create_app`` via ``init_app``. Keeping the limiter here (rather
than as a per-blueprint global) is what lets ``@limiter.limit`` decorators bind
to a real object at import time — the previous per-blueprint ``limiter = None``
pattern silently disabled all rate limits.
"""

import os

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def _resolve_storage_uri() -> str:
    """Pick the rate-limit storage backend from the environment.

    Prefers an explicit RATELIMIT_STORAGE_URI, then a Redis URL (Railway sets
    REDIS_URL), and finally per-process in-memory storage. With Redis, limits
    are exact across all gunicorn workers; in-memory is per-process (~Nx).
    """
    return (
        os.environ.get("RATELIMIT_STORAGE_URI")
        or os.environ.get("REDIS_URL")
        or "memory://"
    )


# Per-IP rate limiter. No global default limits — limits are applied per route
# (the blueprints' rate_limit() helper and @limiter.limit on auth routes).
# in_memory_fallback_enabled keeps the app serving if the Redis backend is
# briefly unreachable. Disabled in tests via RATELIMIT_ENABLED=False.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_resolve_storage_uri(),
    in_memory_fallback_enabled=True,
)
