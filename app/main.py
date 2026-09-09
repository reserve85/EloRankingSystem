"""Elo Ranking System - Main FastAPI Application."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.orm import Session

from app.core.config import BASE_DIR, settings
from app.core.database import SessionLocal, init_db
from app.core.csrf import CSRFMiddleware
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.core.rate_limit import limiter
from app.api.routes.health import router as health_router
from app.api.routes.auth import router as auth_router
from app.api.routes.players import router as players_router
from app.api.routes.matches import router as matches_router
from app.api.routes.rankings import router as rankings_router
from app.api.routes.users import router as users_router
from app.api.routes.settings import router as settings_router
from app.api.routes.reports import router as reports_router
from app.api.routes.audit import router as audit_router
from app.api.routes.password import router as password_router
from app.api.routes.ui import router as ui_router
from app.auth.dependencies import ensure_password_changed
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


# ``/docs``, ``/redoc`` and the OpenAPI schema are only exposed outside
# production (Fix #9); everything else is unchanged.
_is_production = str(settings.app_env).strip().lower() == "production"
app = FastAPI(
    title=settings.app_name,
    description="A dart club ranking system using the Elo Rating System.",
    version="1.0.31",
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
    lifespan=lifespan,
)

# Register CSRF protection (double-submit cookie pattern). Must be added
# after app creation so it wraps all routes, including the UI page renderer.
app.add_middleware(CSRFMiddleware)

# Register rate limiting (brute-force protection for auth endpoints).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Structured request logging with correlation IDs (Fix L11). Added last so it
# is the outermost layer: every request (including CSRF/rate-limit rejections)
# is logged with a request_id echoed in the X-Request-ID response header.
configure_logging()
app.add_middleware(RequestLoggingMiddleware)


@app.exception_handler(FastAPIHTTPException)
async def ui_http_exception_handler(request: Request, exc: FastAPIHTTPException):
    """Redirect unauthenticated UI requests to login instead of returning JSON."""
    if exc.status_code == 401 and request.url.path.startswith("/ui/"):
        return RedirectResponse(url="/ui/login", status_code=302)
    if exc.status_code == 403 and request.url.path.startswith("/ui/"):
        return RedirectResponse(url="/ui/dashboard", status_code=302)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# Mount static files. Anchored to BASE_DIR so the app works regardless of the
# current working directory (Fix M3).
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app/static")), name="static")


# Include API routers. Auth-gated functional routers also require the password
# to have been changed (Fix H2) - a freshly-provisioned SYSTEM bootstrap (or a
# just-reset password) is blocked until the user sets a real password. Auth,
# password and health routers are exempt by design.
def _requires_password_changed():
    return Depends(ensure_password_changed)


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(players_router, dependencies=[_requires_password_changed()])
app.include_router(matches_router, dependencies=[_requires_password_changed()])
app.include_router(rankings_router, dependencies=[_requires_password_changed()])
app.include_router(users_router, dependencies=[_requires_password_changed()])
app.include_router(settings_router, dependencies=[_requires_password_changed()])
app.include_router(reports_router, dependencies=[_requires_password_changed()])
app.include_router(audit_router, dependencies=[_requires_password_changed()])
app.include_router(password_router)

# Include UI router
app.include_router(ui_router)


@app.get("/", include_in_schema=False)
def root_redirect():
    """Redirect root to login page."""
    return RedirectResponse(url="/ui/login")
