"""User repository for database access."""

from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    """Repository for user database operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: int) -> Optional[User]:
        """Get a user by ID."""
        return self.db.query(User).filter(User.id == user_id).first()

    def get_by_username(self, username: str) -> Optional[User]:
        """Get a user by exact username."""
        return self.db.query(User).filter(User.username == username).first()

    def get_all(self) -> list[User]:
        """Get all users ordered by ID."""
        return self.db.query(User).order_by(User.id).all()

    def create(self, user: User) -> User:
        """Stage a new user.

        Only flushes (never commits) so the caller owns the transaction
        boundary: the user and its audit entry commit atomically (Fix L7).
        """
        self.db.add(user)
        self.db.flush()
        return user

    def delete(self, user: User) -> None:
        """Delete a user (may be blocked by a foreign key to an authored match)."""
        self.db.delete(user)
