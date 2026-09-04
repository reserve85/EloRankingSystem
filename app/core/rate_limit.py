"""Centralized rate limiting configuration (Fix #4).

Wraps the ``slowapi`` limiter used to throttle the authentication endpoints
against brute force. The limiter uses in-memory storage keyed by the client's
remote address by default.

Rate limiting can be toggled at runtime via ``limiter.enabled`` (mirrors
``settings.rate_limit_enabled``) which both the decorators and
``SlowAPIMiddleware`` honour per request. This lets tests disable it globally
and re-enable it for dedicated rate-limit tests.
"""

from slowapi import Limiter

from app.core.config import settings
from app.core.request import get_client_ip

# Global limiter. The `enabled` flag is read per-request by both the
# @limiter.limit decorators and the SlowAPIMiddleware, so toggling it at
# runtime (e.g. in tests) takes effect immediately. The key function resolves
# the real client IP, honoring X-Forwarded-For only when a trusted proxy is
# configured (Fix M6), so behind a reverse proxy each client has its own
# budget instead of every user sharing the proxy's.
limiter = Limiter(
    key_func=get_client_ip,
    enabled=settings.rate_limit_enabled,
)

# Per-endpoint rate limits (per implementation plan #4).
LOGIN_LIMIT = "20/minute"
AUTO_LOGIN_LIMIT = "30/minute"
PASSWORD_LIMIT = "5/minute"