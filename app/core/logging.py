"""Structured logging and request correlation (Fix L11).

- :func:`configure_logging` gives the root logger a consistent, timestamped
  format so uvicorn console output and application logs share one style.
- :class:`RequestLoggingMiddleware` emits one line per request carrying a
  ``request_id`` (also stored on ``request.state.request_id``), so operators
  can correlate a failing request with exception tracebacks and audit entries.
  ``/health`` is skipped to keep orchestrator-poll noise out of the logs.
"""

from __future__ import annotations

import logging
import os
import time
import uuid

from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

REQUEST_LOGGER_NAME = "app.request"
# Health probes fire every 30s from the Docker HEALTHCHECK; logging them would
# drown out real traffic.
_SKIP_PATHS = frozenset({"/health"})


def configure_logging() -> None:
    """Configure a consistent, timestamped formatter on the root logger.

    Idempotent: only adds a handler when the root logger has none (tests and
    repeated imports never stack duplicate handlers). The verbosity is taken
    from the ``LOG_LEVEL`` env var (default ``INFO``).
    """
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s %(message)s"))
        root.addHandler(handler)
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    root.setLevel(getattr(logging, level, logging.INFO))


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log one structured line per request and echo an ``X-Request-ID`` header."""

    async def dispatch(self, request: Request, call_next):
        logger = logging.getLogger(REQUEST_LOGGER_NAME)
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id

        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001 - log anything that escapes
            duration_ms = (time.perf_counter() - start) * 1000.0
            if isinstance(exc, RateLimitExceeded):
                logger.warning(
                    "request_rate_limited request_id=%s method=%s path=%s duration_ms=%.1f",
                    request_id,
                    request.method,
                    request.url.path,
                    duration_ms,
                )
            elif getattr(exc, "status_code", None) is not None:
                logger.warning(
                    "request_rejected request_id=%s method=%s path=%s status=%d duration_ms=%.1f",
                    request_id,
                    request.method,
                    request.url.path,
                    exc.status_code,  # type: ignore[attr-defined]
                    duration_ms,
                )
            else:
                logger.exception(
                    "request_failed request_id=%s method=%s path=%s duration_ms=%.1f",
                    request_id,
                    request.method,
                    request.url.path,
                    duration_ms,
                )
            raise

        duration_ms = (time.perf_counter() - start) * 1000.0
        logger.info(
            "request request_id=%s method=%s path=%s status=%d duration_ms=%.1f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        # Best-effort: streaming responses (PDF/QR/logo) may already have
        # started sending, in which case the header cannot be added anymore.
        try:
            response.headers["X-Request-ID"] = request_id
        except Exception:  # noqa: BLE001 - header injection must never 500 a request
            pass
        return response
