"""Authentication service - login, logout, system user provisioning."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.auth.password import hash_password, verify_password
from app.auth.jwt import create_access_token


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    """Authenticate a user by username and password.

    Args:
        db: Database session.
        username: The username to authenticate.
        password: The plain text password to verify.

    Returns:
        User object if authentication succeeds, None otherwise.
    """
    user = db.query(User).filter(User.username == username).first()

    if user is None:
        return None

    if not user.active:
        return None

    if not verify_password(user.password_hash, password):
        return None

    # Update last login timestamp
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    return user


def create_login_response(user: User) -> dict:
    """Create a login response with JWT token.

    Args:
        user: The authenticated User object.

    Returns:
        Dict with access_token, token_type, and user info.
    """
    token = create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role.value,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role.value,
        },
    }


def provision_system_user(db: Session) -> User:
    """Provision the SYSTEM user from configuration.

    Creates the system user if it doesn't exist.
    If it already exists, returns the existing user.

    Args:
        db: Database session.

    Returns:
        The SYSTEM user.
    """
    # Import here to avoid circular imports
    from app.core.config import settings

    existing = db.query(User).filter(
        User.role == UserRole.SYSTEM
    ).first()

    if existing is not None:
        return existing

    system_user = User(
        username=settings.system_user_username,
        password_hash=hash_password(settings.system_user_password),
        role=UserRole.SYSTEM,
        active=True,
    )
    db.add(system_user)
    db.commit()
    db.refresh(system_user)

    return system_user