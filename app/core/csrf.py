"""Double-submit cookie CSRF protection.

Implements the OWASP double-submit cookie pattern as a Starlette/FastAPI
middleware:

1. A random, non-HttpOnly ``csrf_token`` cookie is issued on every response
   where it is not yet present, so that client-side JavaScript can read it.
2. Every state-changing request (POST/PUT/PATCH/DELETE) must echo the token
   back in the ``X-CSRF-Token`` header.
3. The header and cookie are compared in constant time via
   :func:`hmac.compare_digest`.

Only the two endpoints that establish the session are exempt:
``/auth/login`` and ``/auth/auto-login``. They are protected by SameSite
cookies and (optionally) rate limiting instead of CSRF.
"""

from __future__ import annotations

import hmac
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings

# Name of the cookie holding the CSRF token. Deliberately NOT HttpOnly so
# that JavaScript can read it and mirror it into the request header.
CSRF_COOKIE_NAME = "csrf_token"

# Request header that must echo the cookie value on state-changing requests.
CSRF_HEADER_NAME = "X-CSRF-Token"

# HTTP methods that mutate state and therefore require CSRF validation.
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Endpoints exempt from CSRF validation (they establish the session).
CSRF_EXEMPT_PATHS = frozenset({"/auth/login", "/auth/auto-login"})


class CSRFMiddleware(BaseHTTPMiddleware):
    """Enforce a double-submit CSRF token on state-changing requests."""

    def __init__(
        self,
        app,
        cookie_name: str = CSRF_COOKIE_NAME,
        header_name: str = CSRF_HEADER_NAME,
        unsafe_methods: frozenset[str] = UNSAFE_METHODS,
        exempt_paths: frozenset[str] = CSRF_EXEMPT_PATHS,
    ) -> None:
        super().__init__(app)
        self.cookie_name = cookie_name
        self.header_name = header_name
        self.unsafe_methods = unsafe_methods
        self.exempt_paths = exempt_paths

    async def dispatch(self, request: Request, call_next) -> Response:
        """Validate the double-submit token, then delegate, then set the cookie."""
        csrf_cookie = request.cookies.get(self.cookie_name)

        # Validate on every state-changing request unless CSRF is disabled
        # globally or this specific path is exempt.
        if (
            settings.csrf_enabled
            and request.method in self.unsafe_methods
            and request.url.path not in self.exempt_paths
        ):
            header_token = request.headers.get(self.header_name)
            if (
                not csrf_cookie
                or not header_token
                or not self._tokens_match(csrf_cookie, header_token)
            ):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token missing or invalid"},
                )

        response = await call_next(request)

        # Issue the CSRF cookie on the first response that did not already
        # have one. Subsequent page loads read it and echo it back.
        if not csrf_cookie:
            token = secrets.token_urlsafe(32)
            response.set_cookie(
                key=self.cookie_name,
                value=token,
                httponly=False,  # must be readable by JavaScript (apiFetch)
                secure=settings.cookie_secure,
                samesite=settings.cookie_samesite,
                max_age=settings.access_token_lifetime_minutes * 60,
                path="/",
            )

        return response

    @staticmethod
    def _tokens_match(cookie_value: str, header_value: str) -> bool:
        """Compare two ASCII tokens in constant time."""
        return hmac.compare_digest(cookie_value.encode(), header_value.encode())
