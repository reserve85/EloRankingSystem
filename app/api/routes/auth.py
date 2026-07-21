"""Authentication API routes."""

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.auth.dependencies import AUTH_COOKIE_NAME, get_current_user
from app.auth.service import authenticate_user, create_login_response
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login")
def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Authenticate user and set secure HttpOnly cookie.

    Args:
        response: FastAPI response object for setting cookies.
        username: The username to authenticate.
        password: The plain text password.
        db: Database session.

    Returns:
        Login response with user info.

    Raises:
        HTTPException 401: If credentials are invalid.
    """
    user = authenticate_user(db, form_data.username, form_data.password)

    if user is None:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Invalid username or password"},
        )

    login_data = create_login_response(user)

    # Set JWT as secure HttpOnly cookie
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
def logout(response: Response):
    """Clear the authentication cookie.

    Args:
        response: FastAPI response object for clearing cookies.

    Returns:
        Logout confirmation message.
    """
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
    """Get current authenticated user info.

    Args:
        current_user: The authenticated user from cookie.

    Returns:
        Current user information.
    """
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role.value,
        "active": current_user.active,
    }