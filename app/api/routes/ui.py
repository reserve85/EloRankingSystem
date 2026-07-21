"""UI routes for serving HTML templates."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.version import get_version_info
from app.core.templates import templates
from app.auth.dependencies import get_current_user, require_admin
from app.models.user import User

router = APIRouter(prefix="/ui", tags=["ui"])


@router.get("/login")
def login_page(request: Request):
    """Render the login page."""
    return templates.TemplateResponse(
        request,
        "login.html",
        {"app_name": settings.app_name, "version_info": get_version_info()},
    )


@router.get("/dashboard")
def dashboard_page(request: Request, current_user: User = Depends(get_current_user)):
    """Render the user dashboard. All authenticated users."""
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": current_user,
            "app_name": settings.app_name,
            "version_info": get_version_info(),
        },
    )


@router.get("/admin")
def admin_page(request: Request, current_user: User = Depends(require_admin)):
    """Render the admin dashboard. Requires ADMIN or SYSTEM role."""
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "user": current_user,
            "app_name": settings.app_name,
            "version_info": get_version_info(),
        },
    )


@router.get("/change-password")
def change_password_page(request: Request, current_user: User = Depends(get_current_user)):
    """Render the change password page. All authenticated users."""
    return templates.TemplateResponse(
        request,
        "change_password.html",
        {
            "user": current_user,
            "app_name": settings.app_name,
            "version_info": get_version_info(),
        },
    )


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
