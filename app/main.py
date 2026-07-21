"""Elo Ranking System - Main FastAPI Application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal, init_db
from app.api.routes.health import router as health_router
from app.api.routes.auth import router as auth_router
from app.api.routes.players import router as players_router
from app.api.routes.matches import router as matches_router
from app.api.routes.rankings import router as rankings_router
from app.api.routes.users import router as users_router
from app.api.routes.settings import router as settings_router
from app.api.routes.ui import router as ui_router
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

# Include API routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(players_router)
app.include_router(matches_router)
app.include_router(rankings_router)
app.include_router(users_router)
app.include_router(settings_router)

# Include UI router
app.include_router(ui_router)


@app.get("/", include_in_schema=False)
def root_redirect():
    """Redirect root to login page."""
    return RedirectResponse(url="/ui/login")