"""UI routes for serving HTML templates."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.version import get_version_info
from app.core.templates import templates
from app.auth.dependencies import get_current_user, get_optional_user, require_admin
from app.models.user import User
from app.models.club_settings import ClubSettings

router = APIRouter(prefix="/ui", tags=["ui"])


@router.get("/login")
def login_page(request: Request):
    """Render the login page."""
    return templates.TemplateResponse(
        request,
        "login.html",
        {"app_name": settings.app_name, "version_info": get_version_info(settings.timezone)},
    )


def _get_club_name(db: Session) -> str:
    """Get club name from config/env, database, or app_name fallback."""
    if settings.club_name:
        return settings.club_name
    cs = db.query(ClubSettings).first()
    if cs and cs.club_name:
        return cs.club_name
    return settings.app_name


@router.get("/dashboard")
def dashboard_page(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Render the user dashboard. All authenticated users."""
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": current_user,
            "app_name": settings.app_name,
            "club_name": _get_club_name(db),
            "version_info": get_version_info(settings.timezone),
            "hf_min": settings.high_finish_min,
            "hf_max": settings.high_finish_max,
            "ld_min": settings.low_darts_min,
            "ld_max": settings.low_darts_max,
            "timezone": settings.timezone,
        },
    )


@router.get("/admin")
def admin_page(request: Request, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Render the admin dashboard. Requires ADMIN or SYSTEM role."""
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "user": current_user,
            "app_name": settings.app_name,
            "club_name": _get_club_name(db),
            "version_info": get_version_info(settings.timezone),
            "hf_min": settings.high_finish_min,
            "hf_max": settings.high_finish_max,
            "ld_min": settings.low_darts_min,
            "ld_max": settings.low_darts_max,
            "timezone": settings.timezone,
        },
    )


@router.get("/change-password")
def change_password_page(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Render the change password page. All authenticated users."""
    return templates.TemplateResponse(
        request,
        "change_password.html",
        {
            "user": current_user,
            "app_name": settings.app_name,
            "club_name": _get_club_name(db),
            "version_info": get_version_info(settings.timezone),
        },
    )


def _legal_context(db: Session, current_user: User | None = None):
    """Return common context dict for legal pages."""
    ctx = {
        "app_name": settings.app_name,
        "version_info": get_version_info(settings.timezone),
        "contact_company": settings.contact_company,
        "contact_name": settings.contact_name,
        "contact_street": settings.contact_street,
        "contact_city": settings.contact_city,
        "contact_email": settings.contact_email,
    }
    if current_user:
        ctx["user"] = current_user
        ctx["club_name"] = _get_club_name(db)
    return ctx


@router.get("/impressum")
def impressum_page(request: Request, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    """Render the Impressum page. Publicly accessible; logged-in users see full navigation."""
    return templates.TemplateResponse(request, "impressum.html", _legal_context(db, current_user))


@router.get("/privacy")
def privacy_page(request: Request, db: Session = Depends(get_db), current_user: User | None = Depends(get_optional_user)):
    """Render the Privacy Policy page. Publicly accessible; logged-in users see full navigation."""
    return templates.TemplateResponse(request, "privacy.html", _legal_context(db, current_user))


@router.get("/logout")
def logout_redirect(request: Request):
    """Clear auth cookie and redirect to login."""
    from app.core.config import settings as app_settings
    from app.auth.dependencies import AUTH_COOKIE_NAME
    response = RedirectResponse(url="/ui/login", status_code=302)
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path="/",
        httponly=app_settings.cookie_httponly,
        secure=app_settings.cookie_secure,
        samesite=app_settings.cookie_samesite,
    )
    return response
