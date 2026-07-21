"""Player service - business logic for player management."""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.player import Player
from app.repositories.player import PlayerRepository
from app.schemas.player import PlayerCreate, PlayerUpdate


class PlayerService:
    """Service layer for player business logic."""

    def __init__(self, db: Session):
        self.repo = PlayerRepository(db)

    def create_player(self, data: PlayerCreate) -> Player:
        """Create a new player.

        Args:
            data: Player creation data.

        Returns:
            The created player.

        Raises:
            HTTPException 409: If player name already exists.
        """
        existing = self.repo.get_by_name(data.name)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Player with name '{data.name}' already exists",
            )

        start_elo = data.start_elo if data.start_elo is not None else settings.default_elo

        player = Player(
            name=data.name,
            start_elo=start_elo,
            current_elo=float(start_elo),
            active=True,
            disabled=False,
        )

        return self.repo.create(player)

    def get_player(self, player_id: int) -> Player:
        """Get a player by ID.

        Args:
            player_id: The player's ID.

        Returns:
            The player.

        Raises:
            HTTPException 404: If player not found.
        """
        player = self.repo.get_by_id(player_id)
        if player is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Player with id {player_id} not found",
            )
        return player

    def get_all_players(self, include_disabled: bool = False) -> list[Player]:
        """Get all players.

        Args:
            include_disabled: If True, include disabled players.

        Returns:
            List of players.
        """
        return self.repo.get_all(include_disabled=include_disabled)

    def get_active_players(self) -> list[Player]:
        """Get all active, non-disabled players for match selection.

        Returns:
            List of active players.
        """
        return self.repo.get_active()

    def update_player(self, player_id: int, data: PlayerUpdate) -> Player:
        """Update a player's information.

        Args:
            player_id: The player's ID.
            data: Fields to update.

        Returns:
            The updated player.

        Raises:
            HTTPException 404: If player not found.
            HTTPException 409: If new name conflicts with existing player.
        """
        player = self.get_player(player_id)

        if data.name is not None:
            if data.name != player.name:
                existing = self.repo.get_by_name(data.name)
                if existing is not None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Player with name '{data.name}' already exists",
                    )
            player.name = data.name

        if data.start_elo is not None:
            player.start_elo = data.start_elo

        return self.repo.update(player)

    def disable_player(self, player_id: int) -> Player:
        """Disable a player.

        Disabled players:
        - Cannot be selected for new matches (by default)
        - Remain in the database
        - Retain all Elo history
        - Remain available in historical reports

        Args:
            player_id: The player's ID.

        Returns:
            The disabled player.
        """
        player = self.get_player(player_id)
        player.disabled = True
        player.active = False
        return self.repo.update(player)

    def reactivate_player(self, player_id: int) -> Player:
        """Reactivate a disabled player.

        Args:
            player_id: The player's ID.

        Returns:
            The reactivated player.
        """
        player = self.get_player(player_id)
        player.disabled = False
        player.active = True
        return self.repo.update(player)