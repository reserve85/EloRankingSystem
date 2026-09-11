"""Player service - business logic for player management."""

from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.player import Player
from app.models.player_disable_period import PlayerDisablePeriod
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
        # Fix #3 II: member-since date. Defaults to today's date when omitted
        # so new players become rankable from the day they are created.
        entry_date = data.entry_date if data.entry_date is not None else date.today()

        player = Player(
            name=data.name,
            start_elo=start_elo,
            current_elo=float(start_elo),
            entry_date=entry_date,
            active=False,
            disabled=False,
        )

        player = self.repo.create(player)
        # The repository already flushed (id assigned). The caller (API route)
        # owns the transaction boundary and commits once after the audit log,
        # so the player and its audit entry are written atomically (Fix L7).
        return player

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

        If start_elo changes, a full Elo recalculation is triggered
        for all matches involving this player.

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
        start_elo_changed = False

        if data.name is not None:
            if data.name != player.name:
                existing = self.repo.get_by_name(data.name)
                if existing is not None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Player with name '{data.name}' already exists",
                    )
            player.name = data.name

        if data.start_elo is not None and data.start_elo != player.start_elo:
            player.start_elo = data.start_elo
            start_elo_changed = True

        if data.entry_date is not None:
            player.entry_date = data.entry_date

        player = self.repo.update(player)

        # Trigger full Elo recalculation if start_elo changed
        if start_elo_changed:
            from app.services.match import MatchService

            match_service = MatchService(self.repo.db)
            match_service.recalculate_elo_timeline({player_id})

        # No commit here: the caller (API route) owns the transaction boundary
        # and commits once after the audit log, keeping the mutation, the Elo
        # recalculation, and the audit entry in a single transaction (Fix L7).
        return player

    def disable_player(self, player_id: int) -> Player:
        """Disable a player.

        Disabled players:
        - Cannot be selected for new matches (by default)
        - Remain in the database
        - Retain all Elo history
        - Remain available in historical reports

        Record of the disablement (Fix #5): a new open disable period
        ("from today on") is stored, so the history-aware rankings only
        exclude the player on dates the disable was actually active. Old
        rankings before today keep counting the player, i.e. disabling a
        top player never retroactively improves anyone else's Best Rank.

        Args:
            player_id: The player's ID.

        Returns:
            The disabled player.
        """
        player = self.get_player(player_id)
        if not player.disabled:
            open_period = (
                self.repo.db.query(PlayerDisablePeriod)
                .filter(
                    PlayerDisablePeriod.player_id == player.id,
                    PlayerDisablePeriod.disabled_to.is_(None),
                )
                .first()
            )
            if open_period is None:
                self.repo.db.add(
                    PlayerDisablePeriod(
                        player_id=player.id,
                        disabled_from=date.today(),
                        disabled_to=None,
                    )
                )
        player.disabled = True
        player.active = False
        player = self.repo.update(player)
        return player

    def reactivate_player(self, player_id: int) -> Player:
        """Reactivate a disabled player.

        Closes the player's currently open disable period the day BEFORE the
        reactivation (Fix #5), so the player is excluded up to and including
        yesterday and reappears in the rankings the SAME day they are
        re-enabled. The exact window is recorded for the history-aware
        rankings; a player disabled Jan-Feb, re-enabled and disabled again
        later therefore accumulates multiple windows that are each evaluated
        separately.

        A disable + immediate re-enable on the SAME day is a no-op toggle:
        the player is not disabled for a single whole day, so the window is
        DELETED instead of persist. Storing an empty window (disabled_from
        ``today``, disabled_to ``today - 1``) would otherwise accumulate a
        junk row per toggle and could poison the ranking when combined with
        legacy same-day windows (``[today, today]``) written by the original
        Fix #5 code.

        Args:
            player_id: The player's ID.

        Returns:
            The reactivated player.
        """
        player = self.get_player(player_id)
        if player.disabled:
            open_period = (
                self.repo.db.query(PlayerDisablePeriod)
                .filter(
                    PlayerDisablePeriod.player_id == player.id,
                    PlayerDisablePeriod.disabled_to.is_(None),
                )
                .first()
            )
            if open_period is not None:
                if open_period.disabled_from == date.today():
                    # Disabled and re-enabled on the same calendar day: there
                    # is no day on which the player was actually missing, so
                    # drop the period instead of recording an empty window.
                    self.repo.db.delete(open_period)
                else:
                    # Close the window the day BEFORE the reactivation: the
                    # inclusive window semantics would otherwise keep the
                    # player hidden for the whole re-enable day.
                    open_period.disabled_to = date.today() - timedelta(days=1)
        player.disabled = False
        player.active = True
        player = self.repo.update(player)
        return player
