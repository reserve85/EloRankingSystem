"""Elo Ranking System - Main FastAPI Application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, init_db
from app.api.routes.health import router as health_router
from app.api.routes.auth import router as auth_router
from app.api.routes.players import router as players_router
from app.auth.service import provision_system_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown events."""
    # Startup: create tables and provision system user
    init_db()
    db: Session = SessionLocal()
    try:
        provision_system_user(db)
    finally:
        db.close()

    yield
    # Shutdown


app = FastAPI(
    title=settings.app_name,
    description="A dart club ranking system using the Elo Rating System.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(players_router)
