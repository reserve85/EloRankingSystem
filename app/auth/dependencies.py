"""FastAPI dependencies for authentication and authorization."""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User, UserRole
from app.auth.jwt import decode_access_token

# Cookie name for the JWT token
AUTH_COOKIE_NAME = "access_token"


def get_token_from_cookie(request: Request) -> str | None:
    """Extract JWT token from HttpOnly cookie.

    Args:
        request: The FastAPI request object.

    Returns:
        Token string if present, None otherwise.
    """
    return request.cookies.get(AUTH_COOKIE_NAME)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Dependency to get the current authenticated user from cookie.

    Args:
        request: The FastAPI request object.
        db: Database session.

    Returns:
        The authenticated User object.

    Raises:
        HTTPException 401: If token is missing, invalid, or user not found.
    """
    token = get_token_from_cookie(request)

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    user = db.query(User).filter(User.id == int(user_id)).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return user


def get_optional_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User | None:
    """Dependency to get the current user if authenticated, None otherwise.

    Unlike get_current_user, this does NOT raise 401 if no valid token exists.
    Used for pages that are publicly accessible but show navigation for logged-in users.

    Args:
        request: The FastAPI request object.
        db: Database session.

    Returns:
        The authenticated User object, or None if not authenticated.
    """
    token = get_token_from_cookie(request)

    if token is None:
        return None

    payload = decode_access_token(token)

    if payload is None:
        return None

    user_id = payload.get("sub")
    if user_id is None:
        return None

    user = db.query(User).filter(User.id == int(user_id)).first()

    if user is None or not user.active:
        return None

    return user


def ensure_password_changed(current_user: User = Depends(get_current_user)) -> User:
    """Block a user who must first change their password (Fix H2).

    Used as a router-level dependency on auth-gated API endpoints. When
    ``must_change_password`` is set (right after SYSTEM bootstrap provision or an
    admin password reset), the user is forced to set a new password before using
    the system. The exempt surface (login/logout, the change-password endpoint
    and page) must not use this dependency.

    Args:
        current_user: The authenticated user (from the auth cookie).

    Returns:
        The current user when no password change is required.

    Raises:
        HTTPException 403: If the user must change their password first.
    """
    if current_user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A password change is required before using this resource",
        )
    return current_user


def require_role(*roles: UserRole):
    """Dependency factory to require specific user roles.

    Args:
        *roles: Allowed roles (UserRole.SYSTEM, UserRole.ADMIN, UserRole.USER).

    Returns:
        A dependency function that checks the current user's role.

    Raises:
        HTTPException 403: If user's role is not in the allowed roles.
    """

    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role(s): {[r.value for r in roles]}",
            )
        return current_user

    return role_checker


# Pre-built role dependencies for convenience
require_system = require_role(UserRole.SYSTEM)
require_admin = require_role(UserRole.SYSTEM, UserRole.ADMIN)
require_user = require_role(UserRole.SYSTEM, UserRole.ADMIN, UserRole.USER)
