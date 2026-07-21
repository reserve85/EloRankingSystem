"""Authentication API routes."""

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.auth.dependencies import AUTH_COOKIE_NAME, get_current_user
from app.auth.service import authenticate_user, create_login_response
from app.models.user import User
from app.services.audit import log_event, get_client_info

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login")
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Authenticate user and set secure HttpOnly cookie."""
    ip, ua = get_client_info(request)
    user = authenticate_user(db, form_data.username, form_data.password)

    if user is None:
        log_event(
            db, action="LOGIN_FAILED", entity_type="user",
            username=form_data.username,
            new_value={"username": form_data.username},
            ip_address=ip, user_agent=ua,
        )
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Invalid username or password"},
        )

    login_data = create_login_response(user)

    log_event(
        db, action="LOGIN", entity_type="user",
        user_id=user.id, username=user.username,
        ip_address=ip, user_agent=ua,
    )

    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=login_data["access_token"],
        httponly=settings.cookie_httponly,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.access_token_lifetime_minutes * 60,
        path="/",
    )

    return login_data


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """Clear the authentication cookie."""
    ip, ua = get_client_info(request)

    # Try to get current user for logging
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if token:
        from app.auth.jwt import decode_access_token
        payload = decode_access_token(token)
        if payload:
            log_event(
                db, action="LOGOUT", entity_type="user",
                user_id=int(payload.get("sub", 0)),
                username=payload.get("username"),
                ip_address=ip, user_agent=ua,
            )

    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path="/",
        httponly=settings.cookie_httponly,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )

    return {"message": "Logged out successfully"}


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role.value,
        "active": current_user.active,
    }
