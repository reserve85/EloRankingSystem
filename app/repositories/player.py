"""Player repository for database access."""

from typing import Optional

from sqlalchemy.orm import Session

from app.models.player import Player


class PlayerRepository:
    """Repository for player database operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, player_id: int) -> Optional[Player]:
        """Get a player by ID."""
        return self.db.query(Player).filter(Player.id == player_id).first()

    def get_all(self, include_disabled: bool = False) -> list[Player]:
        """Get all players.

        Args:
            include_disabled: If True, include disabled players.
        """
        query = self.db.query(Player)
        if not include_disabled:
            query = query.filter(Player.disabled.is_(False))
        return query.order_by(Player.name).all()

    def get_active(self) -> list[Player]:
        """Get all non-disabled players for match selection.

        Returns both active and inactive (but not disabled) players,
        so inactive players can be selected for their first match.
        """
        return (
            self.db.query(Player)
            .filter(Player.disabled.is_(False))
            .order_by(Player.name)
            .all()
        )

    def get_by_name(self, name: str) -> Optional[Player]:
        """Get a player by exact name."""
        return self.db.query(Player).filter(Player.name == name).first()

    def create(self, player: Player) -> Player:
        """Create a new player."""
        self.db.add(player)
        self.db.commit()
        self.db.refresh(player)
        return player

    def update(self, player: Player) -> Player:
        """Update an existing player."""
        self.db.commit()
        self.db.refresh(player)
        return player

    def delete(self, player: Player) -> None:
        """Delete a player (should only be used if no match history)."""
        self.db.delete(player)
        self.db.commit()
