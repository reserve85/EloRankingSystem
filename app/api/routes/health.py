"""Health check endpoint."""

from datetime import datetime, timezone

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.core.database import engine

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(response: Response):
    """Health check endpoint.

    Validates the database with a cheap ``SELECT 1`` so an orchestrator (the
    Docker HEALTHCHECK) can detect an unreachable or corrupted database and
    restart the container (Fix L2). A failure returns HTTP 503.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any DB failure means unhealthy
        response.status_code = 503
        return {
            "status": "unhealthy",
            "detail": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


