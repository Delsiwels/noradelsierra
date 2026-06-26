"""Shared Flask extension singletons (app-factory pattern).

Instantiated unbound at import time and bound to the application in
``webapp.app.create_app`` via ``init_app``. Keeping the limiter here (rather
than as a per-blueprint global) is what lets ``@limiter.limit`` decorators bind
to a real object at import time — the previous per-blueprint ``limiter = None``
pattern silently disabled all rate limits.
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Per-IP rate limiter. No global default limits — limits are applied per route
# (the blueprints' rate_limit() helper and @limiter.limit on auth routes).
# In-memory storage is per-process; with multiple gunicorn workers the effective
# limit is approximately (limit x workers). Disabled in tests via
# RATELIMIT_ENABLED=False (see TestingConfig).
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
