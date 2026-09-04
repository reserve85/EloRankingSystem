"""Health check endpoint."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.core.database import engine

router = APIRouter(tags=["health"])

_logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check(response: Response):
    """Health check endpoint.

    Validates the database with a cheap ``SELECT 1`` so an orchestrator (the
    Docker HEALTHCHECK) can detect an unreachable or corrupted database and
    restart the container (Fix L2). A failure returns HTTP 503. The raw
    exception is logged server-side but never echoed to unauthenticated
    callers, who might otherwise learn driver/database internals (Fix L1).
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - any DB failure means unhealthy
        _logger.exception("Health check database probe failed")
        response.status_code = 503
        return {
            "status": "unhealthy",
            "detail": "database unavailable",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
