"""JWT token creation and verification."""

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.core.config import settings


def create_access_token(
    user_id: int,
    username: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token.

    Args:
        user_id: The user's database ID.
        username: The user's username.
        role: The user's role (SYSTEM, ADMIN, USER).
        expires_delta: Optional custom expiration time.

    Returns:
        Encoded JWT string.
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.access_token_lifetime_minutes)

    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + expires_delta,
    }

    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and verify a JWT access token.

    Args:
        token: The JWT string to decode.

    Returns:
        Decoded payload dict if valid, None if expired or invalid.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None