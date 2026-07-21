"""Password hashing and verification using Argon2."""

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

# Argon2 password hasher with default settings
_ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password using Argon2.

    Args:
        password: Plain text password to hash.

    Returns:
        Argon2 hash string.
    """
    return _ph.hash(password)


def verify_password(hash_str: str, password: str) -> bool:
    """Verify a password against an Argon2 hash.

    Args:
        hash_str: The stored Argon2 hash.
        password: The plain text password to verify.

    Returns:
        True if password matches, False otherwise.
    """
    try:
        return _ph.verify(hash_str, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(hash_str: str) -> bool:
    """Check if a password hash needs to be rehashed (parameters changed).

    Args:
        hash_str: The stored Argon2 hash.

    Returns:
        True if rehash is needed, False otherwise.
    """
    try:
        return _ph.check_needs_rehash(hash_str)
    except (InvalidHashError, Exception):
        return True