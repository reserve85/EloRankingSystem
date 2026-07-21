"""Match service - business logic for match management with Elo calculation."""

from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.match import Match
from app.models.audit_log import AuditLog
from app.repositories.match import MatchRepository
from app.repositories.player import PlayerRepository
from app.schemas.match import MatchCreate, MatchUpdate
from app.services.elo import calculate_match_elo


class MatchService:
    """Service layer for match business logic."""

    def __init__(self, db: Session):
        self.db = db
        self.match_repo = MatchRepository(db)
        self.player_repo = PlayerRepository(db)

    def create_match(self, data: MatchCreate, created_by: int | None = None) -> Match:
        """Create a new match, calculate Elo, update players, log audit.

        Args:
            data: Match creation data.
            created_by: ID of the user creating the match.

        Returns:
            The created match with all Elo data stored.

        Raises:
            HTTPException 404: If either player not found.
            HTTPException 400: If validation fails.
        """
        # Fetch players
        player_a = self.player_repo.get_by_id(data.player_a_id)
        if player_a is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Player A (id={data.player_a_id}) not found",
            )

        player_b = self.player_repo.get_by_id(data.player_b_id)
        if player_b is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Player B (id={data.player_b_id}) not found",
            )

        if data.player_a_id == data.player_b_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Player A and Player B cannot be the same player",
            )

        if data.winner_id not in (data.player_a_id, data.player_b_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Winner must be either Player A or Player B",
            )

        # Determine winner label for Elo calculation
        winner_label = "A" if data.winner_id == data.player_a_id else "B"
        loser_id = data.player_b_id if winner_label == "A" else data.player_a_id

        # Calculate Elo
        elo_result = calculate_match_elo(
            rating_a=player_a.current_elo,
            rating_b=player_b.current_elo,
            winner=winner_label,
        )

        # Create match record
        match = Match(
            date=data.date,
            player_a_id=data.player_a_id,
            player_b_id=data.player_b_id,
            winner_id=data.winner_id,
            loser_id=loser_id,
            elo_before_a=player_a.current_elo,
            elo_before_b=player_b.current_elo,
            elo_after_a=elo_result.new_rating_a,
            elo_after_b=elo_result.new_rating_b,
            elo_change_a=elo_result.change_a,
            elo_change_b=elo_result.change_b,
            created_by=created_by,
        )
        match = self.match_repo.create(match)

        # Update player current Elo and last match date
        player_a.current_elo = elo_result.new_rating_a
        player_a.last_match_date = data.date
        player_b.current_elo = elo_result.new_rating_b
        player_b.last_match_date = data.date
        self.db.commit()

        # Create audit log entry
        audit = AuditLog(
            user_id=created_by,
            action="MATCH_CREATED",
            entity_type="match",
            entity_id=match.id,
            old_value=None,
            new_value=(
                f'{{"player_a": {data.player_a_id}, "player_b": {data.player_b_id}, '
                f'"winner": {data.winner_id}, "date": "{data.date}"}}'
            ),
        )
        self.db.add(audit)
        self.db.commit()

        return match

    def get_match(self, match_id: int) -> Match:
        """Get a match by ID.

        Args:
            match_id: The match's ID.

        Returns:
            The match.

        Raises:
            HTTPException 404: If match not found.
        """
        match = self.match_repo.get_by_id(match_id)
        if match is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Match with id {match_id} not found",
            )
        return match

    def get_all_matches(
        self,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[Match]:
        """Get all matches, optionally filtered by date range."""
        return self.match_repo.get_all(from_date=from_date, to_date=to_date)

    def get_player_matches(self, player_id: int) -> list[Match]:
        """Get all matches for a specific player."""
        return self.match_repo.get_by_player(player_id)

    def delete_match(self, match_id: int, deleted_by: int | None = None) -> None:
        """Delete a match (ADMIN/SYSTEM only).

        Note: Historical Elo recalculation is not yet implemented.
        This will be added in a future milestone.

        Args:
            match_id: The match's ID.
            deleted_by: ID of the user deleting the match.
        """
        match = self.get_match(match_id)

        # Create audit log before deletion
        audit = AuditLog(
            user_id=deleted_by,
            action="MATCH_DELETED",
            entity_type="match",
            entity_id=match.id,
            old_value=(
                f'{{"player_a": {match.player_a_id}, "player_b": {match.player_b_id}, '
                f'"winner": {match.winner_id}, "date": "{match.date}"}}'
            ),
            new_value=None,
        )
        self.db.add(audit)
        self.db.commit()

        self.match_repo.delete(match)