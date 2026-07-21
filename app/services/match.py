"""Match service - business logic for match management with Elo recalculation.

Historical Elo recalculation:
When a match is added, edited, or deleted, the complete affected timeline
is recalculated chronologically. Matches are sorted by:
    Date ASC, Created At ASC, ID ASC
to ensure deterministic Elo calculations.
"""

from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.match import Match
from app.models.player import Player
from app.models.audit_log import AuditLog
from app.repositories.match import MatchRepository
from app.repositories.player import PlayerRepository
from app.schemas.match import MatchCreate, MatchUpdate
from app.services.elo import calculate_match_elo


class MatchService:
    """Service layer for match business logic with historical recalculation."""

    def __init__(self, db: Session):
        self.db = db
        self.match_repo = MatchRepository(db)
        self.player_repo = PlayerRepository(db)

    def create_match(self, data: MatchCreate, created_by: int | None = None) -> Match:
        """Create a new match, then recalculate the affected Elo timeline.

        Args:
            data: Match creation data.
            created_by: ID of the user creating the match.

        Returns:
            The created match with all Elo data stored.

        Raises:
            HTTPException 404: If either player not found.
            HTTPException 400: If validation fails.
        """
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

        winner_label = "A" if data.winner_id == data.player_a_id else "B"
        loser_id = data.player_b_id if winner_label == "A" else data.player_a_id

        # Create match with placeholder Elo (will be overwritten by recalculation)
        match = Match(
            date=data.date,
            player_a_id=data.player_a_id,
            player_b_id=data.player_b_id,
            winner_id=data.winner_id,
            loser_id=loser_id,
            elo_before_a=0.0,
            elo_before_b=0.0,
            elo_after_a=0.0,
            elo_after_b=0.0,
            elo_change_a=0.0,
            elo_change_b=0.0,
            created_by=created_by,
        )
        match = self.match_repo.create(match)

        # Recalculate the full affected timeline
        self._recalculate_elo_timeline({data.player_a_id, data.player_b_id})

        # Refresh and return
        self.db.refresh(match)

        # Audit log
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

    def update_match(
        self, match_id: int, data: MatchUpdate, updated_by: int | None = None
    ) -> Match:
        """Update a match and recalculate the affected Elo timeline.

        Args:
            match_id: The match's ID.
            data: Fields to update.
            updated_by: ID of the user updating the match.

        Returns:
            The updated match.

        Raises:
            HTTPException 404: If match not found.
        """
        match = self.get_match(match_id)

        old_value = (
            f'{{"date": "{match.date}", "winner_id": {match.winner_id}, '
            f'"player_a": {match.player_a_id}, "player_b": {match.player_b_id}}}'
        )

        affected_players = {match.player_a_id, match.player_b_id}

        if data.date is not None:
            match.date = data.date

        if data.winner_id is not None:
            if data.winner_id not in (match.player_a_id, match.player_b_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Winner must be either Player A or Player B",
                )
            match.winner_id = data.winner_id
            match.loser_id = (
                match.player_b_id
                if data.winner_id == match.player_a_id
                else match.player_a_id
            )

        self.db.commit()

        # Recalculate the full affected timeline
        self._recalculate_elo_timeline(affected_players)

        # Refresh and return
        self.db.refresh(match)

        new_value = (
            f'{{"date": "{match.date}", "winner_id": {match.winner_id}, '
            f'"player_a": {match.player_a_id}, "player_b": {match.player_b_id}}}'
        )

        audit = AuditLog(
            user_id=updated_by,
            action="MATCH_UPDATED",
            entity_type="match",
            entity_id=match.id,
            old_value=old_value,
            new_value=new_value,
        )
        self.db.add(audit)
        self.db.commit()

        return match

    def get_match(self, match_id: int) -> Match:
        """Get a match by ID."""
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
        """Delete a match and recalculate the affected Elo timeline.

        Args:
            match_id: The match's ID.
            deleted_by: ID of the user deleting the match.
        """
        match = self.get_match(match_id)

        affected_players = {match.player_a_id, match.player_b_id}

        # Audit log before deletion
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

        # Recalculate the full affected timeline
        self._recalculate_elo_timeline(affected_players)

    def _recalculate_elo_timeline(self, affected_player_ids: set[int]) -> None:
        """Recalculate the Elo timeline for all affected players.

        This is the core of historical Elo recalculation. When any match
        involving the affected players is created, edited, or deleted:

        1. Find the earliest match involving any affected player.
        2. From that date, get ALL matches chronologically.
        3. Collect ALL players who appear in those matches.
        4. Reset all those players to their start_elo.
        5. Recalculate all matches in order, updating Elo snapshots.
        6. Update all player current_elo and last_match_date.

        Args:
            affected_player_ids: Set of player IDs directly affected.
        """
        if not affected_player_ids:
            return

        # Step 1: Find the earliest match involving any affected player
        earliest_match = None
        for pid in affected_player_ids:
            player_matches = self.match_repo.get_by_player(pid)
            if player_matches:
                candidate = player_matches[0]  # Already sorted by date ASC
                if earliest_match is None or (
                    candidate.date, candidate.created_at, candidate.id
                ) < (earliest_match.date, earliest_match.created_at, earliest_match.id):
                    earliest_match = candidate

        if earliest_match is None:
            # No matches left for affected players, reset their Elo to start
            for pid in affected_player_ids:
                player = self.player_repo.get_by_id(pid)
                if player is not None:
                    player.current_elo = float(player.start_elo)
                    player.last_match_date = None
            self.db.commit()
            return

        # Step 2: From the earliest affected date, get ALL matches chronologically
        all_matches = self.match_repo.get_all(from_date=earliest_match.date)

        # Also include matches on the same date but created before
        # (the repo already sorts by date ASC, created_at ASC, id ASC)
        # We need all matches from the earliest match onwards
        # Filter: keep matches where date >= earliest_match.date
        # BUT for same date, we need those with earlier created_at too
        # Safer: get all matches from earliest date, the sort handles the rest
        all_matches = [
            m for m in all_matches
            if (m.date, m.created_at, m.id) >= (
                earliest_match.date,
                earliest_match.created_at if m.date == earliest_match.date else None,
                0 if m.date != earliest_match.date else earliest_match.id,
            )
        ]

        # Actually, simpler: get all matches from the beginning to be safe
        # and recalculate only from the earliest affected match onwards
        all_matches_from_start = self.match_repo.get_all()

        # Find the index of the earliest match in the full timeline
        start_idx = 0
        for i, m in enumerate(all_matches_from_start):
            if m.id == earliest_match.id:
                start_idx = i
                break

        # Get all matches from the earliest affected point onwards
        matches_to_recalc = all_matches_from_start[start_idx:]

        if not matches_to_recalc:
            return

        # Step 3: Collect ALL players who appear in ANY of those matches
        player_ids_in_timeline: set[int] = set()
        for m in matches_to_recalc:
            player_ids_in_timeline.add(m.player_a_id)
            player_ids_in_timeline.add(m.player_b_id)

        # Step 4: Reset all those players to their start_elo
        players: dict[int, Player] = {}
        for pid in player_ids_in_timeline:
            player = self.player_repo.get_by_id(pid)
            if player is not None:
                player.current_elo = float(player.start_elo)
                player.last_match_date = None
                players[pid] = player

        # Step 5: Recalculate all matches in chronological order
        # Re-sort to ensure deterministic order
        matches_to_recalc.sort(key=lambda m: (m.date, m.created_at, m.id))

        for m in matches_to_recalc:
            pa = players.get(m.player_a_id)
            pb = players.get(m.player_b_id)

            if pa is None or pb is None:
                continue

            winner_label = "A" if m.winner_id == m.player_a_id else "B"

            elo_result = calculate_match_elo(
                rating_a=pa.current_elo,
                rating_b=pb.current_elo,
                winner=winner_label,
            )

            # Update match Elo snapshots
            m.elo_before_a = pa.current_elo
            m.elo_before_b = pb.current_elo
            m.elo_after_a = elo_result.new_rating_a
            m.elo_after_b = elo_result.new_rating_b
            m.elo_change_a = elo_result.change_a
            m.elo_change_b = elo_result.change_b

            # Update player current Elo
            pa.current_elo = elo_result.new_rating_a
            pb.current_elo = elo_result.new_rating_b

            # Update last_match_date (keep the latest)
            pa.last_match_date = m.date
            pb.last_match_date = m.date

        # Step 6: Commit all changes in a single transaction
        self.db.commit()

        # Audit log for recalculation
        audit = AuditLog(
            action="RANKING_RECALCULATED",
            entity_type="ranking",
            entity_id=None,
            old_value=None,
            new_value=(
                f'{{"affected_players": {list(affected_player_ids)}, '
                f'"matches_recalculated": {len(matches_to_recalc)}}}'
            ),
        )
        self.db.add(audit)
        self.db.commit()