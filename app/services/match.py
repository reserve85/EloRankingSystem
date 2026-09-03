"""Match service - business logic for match management with Elo recalculation.

Historical Elo recalculation:
When a match is added, edited, or deleted, the complete affected timeline
is recalculated chronologically. Matches are sorted by:
    Date ASC, Created At ASC, ID ASC
to ensure deterministic Elo calculations.

Best-of-5 scoring:
    Valid scores: 3:0, 3:1, 3:2, 2:3, 1:3, 0:3
    Winner is the player with score 3.
"""

from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.match import Match
from app.models.player import Player
from app.models.audit_log import AuditLog
from app.core.config import settings
from app.repositories.match import MatchRepository
from app.repositories.player import PlayerRepository
from app.schemas.match import MatchCreate, MatchUpdate, determine_winner
from app.services.elo import calculate_match_elo


class MatchService:
    """Service layer for match business logic with historical recalculation."""

    def __init__(self, db: Session):
        self.db = db
        self.match_repo = MatchRepository(db)
        self.player_repo = PlayerRepository(db)

    def check_duplicate(
        self,
        player_a_id: int,
        player_b_id: int,
        player1_score: int,
        player2_score: int,
        match_date,
        exclude_match_id: int | None = None,
    ) -> Match | None:
        """Check for duplicate match with same players, exact score, and date.

        Args:
            player_a_id: ID of player A
            player_b_id: ID of player B
            player1_score: Score of player A
            player2_score: Score of player B
            match_date: Date of the match
            exclude_match_id: Optional match ID to exclude (for updates)

        Returns:
            Duplicate match if found, None otherwise.
        """
        return self.match_repo.get_duplicate_match(
            player_a_id=player_a_id,
            player_b_id=player_b_id,
            player1_score=player1_score,
            player2_score=player2_score,
            match_date=match_date,
            exclude_match_id=exclude_match_id,
        )

    def create_match(self, data: MatchCreate, created_by: int | None = None, username: str | None = None, force: bool = False) -> Match:
        """Create a new match using Best-of-5 scores, then recalculate.

        Args:
            data: Match creation data
            created_by: ID of user creating the match
            username: Username of user creating the match
            force: If True, skip duplicate check and save anyway.
        """
        player_a = self.player_repo.get_by_id(data.player_a_id)
        if player_a is None:
            raise HTTPException(status_code=404, detail=f"Player A (id={data.player_a_id}) not found")

        player_b = self.player_repo.get_by_id(data.player_b_id)
        if player_b is None:
            raise HTTPException(status_code=404, detail=f"Player B (id={data.player_b_id}) not found")

        if data.player_a_id == data.player_b_id:
            raise HTTPException(status_code=400, detail="Player A and Player B cannot be the same player")

        # Determine winner from scores
        bol = data.best_of_legs if data.best_of_legs > 0 else settings.best_of_legs
        winner_label = determine_winner(data.player1_score, data.player2_score, bol)
        winner_id = data.player_a_id if winner_label == 1 else data.player_b_id
        loser_id = data.player_b_id if winner_label == 1 else data.player_a_id

        # Check for duplicate match (same players, exact score, date)
        if not force:
            duplicate = self.check_duplicate(
                player_a_id=data.player_a_id,
                player_b_id=data.player_b_id,
                player1_score=data.player1_score,
                player2_score=data.player2_score,
                match_date=data.date,
            )
            if duplicate is not None:
                raise HTTPException(
                    status_code=409,
                    detail="A match with the same result on the same day already exists. Do you want to save it anyway?"
                )

        # Create match with placeholder Elo and statistics
        match = Match(
            date=data.date,
            player_a_id=data.player_a_id,
            player_b_id=data.player_b_id,
            best_of_legs=bol,
            player1_score=data.player1_score,
            player2_score=data.player2_score,
            winner_id=winner_id,
            loser_id=loser_id,
            elo_before_a=0.0, elo_before_b=0.0,
            elo_after_a=0.0, elo_after_b=0.0,
            elo_change_a=0.0, elo_change_b=0.0,
            k_factor=float(settings.k_factor),
            player_a_180s=data.player_a_180s,
            player_b_180s=data.player_b_180s,
            player_a_high_finishes=data.player_a_high_finishes,
            player_b_high_finishes=data.player_b_high_finishes,
            player_a_low_darts=data.player_a_low_darts,
            player_b_low_darts=data.player_b_low_darts,
            player_a_average=data.player_a_average,
            player_b_average=data.player_b_average,
            created_by=created_by,
        )
        match = self.match_repo.create(match)

        self._recalculate_elo_timeline({data.player_a_id, data.player_b_id}, created_by, username)
        self.db.refresh(match)

        audit = AuditLog(
            user_id=created_by, username=username, action="MATCH_CREATED", entity_type="match",
            entity_id=match.id, old_value=None,
            new_value=f'{{"player_a": {data.player_a_id}, "player_b": {data.player_b_id}, "score": "{data.player1_score}:{data.player2_score}", "winner": {winner_id}, "date": "{data.date}", "statistics": {{"180s_a": {data.player_a_180s}, "180s_b": {data.player_b_180s}, "high_finishes_a": {data.player_a_high_finishes}, "high_finishes_b": {data.player_b_high_finishes}, "low_darts_a": {data.player_a_low_darts}, "low_darts_b": {data.player_b_low_darts}, "average_a": {data.player_a_average}, "average_b": {data.player_b_average}}}}}',
        )
        self.db.add(audit)
        self.db.commit()
        return match

    def update_match(self, match_id: int, data: MatchUpdate, updated_by: int | None = None, username: str | None = None) -> Match:
        """Update a match and recalculate the affected Elo timeline."""
        match = self.get_match(match_id)
        old_value = f'{{"date": "{match.date}", "score": "{match.player1_score}:{match.player2_score}", "winner_id": {match.winner_id}, "player_a": {match.player_a_id}, "player_b": {match.player_b_id}, "statistics": {{"180s_a": {match.player_a_180s}, "180s_b": {match.player_b_180s}, "high_finishes_a": {match.player_a_high_finishes}, "high_finishes_b": {match.player_b_high_finishes}, "low_darts_a": {match.player_a_low_darts}, "low_darts_b": {match.player_b_low_darts}, "average_a": {match.player_a_average}, "average_b": {match.player_b_average}}}}}'
        affected_players = {match.player_a_id, match.player_b_id}

        if data.date is not None:
            match.date = data.date

        if data.player1_score is not None and data.player2_score is not None:
            bol = data.best_of_legs if data.best_of_legs and data.best_of_legs > 0 else match.best_of_legs
            winner_label = determine_winner(data.player1_score, data.player2_score, bol)
            if data.best_of_legs and data.best_of_legs > 0:
                match.best_of_legs = data.best_of_legs
            match.player1_score = data.player1_score
            match.player2_score = data.player2_score
            match.winner_id = match.player_a_id if winner_label == 1 else match.player_b_id
            match.loser_id = match.player_b_id if winner_label == 1 else match.player_a_id

        # Update statistics if provided
        if data.player_a_180s is not None:
            match.player_a_180s = data.player_a_180s
        if data.player_b_180s is not None:
            match.player_b_180s = data.player_b_180s
        if data.player_a_high_finishes is not None:
            match.player_a_high_finishes = data.player_a_high_finishes
        if data.player_b_high_finishes is not None:
            match.player_b_high_finishes = data.player_b_high_finishes
        if data.player_a_low_darts is not None:
            match.player_a_low_darts = data.player_a_low_darts
        if data.player_b_low_darts is not None:
            match.player_b_low_darts = data.player_b_low_darts
        if data.player_a_average is not None:
            match.player_a_average = data.player_a_average
        if data.player_b_average is not None:
            match.player_b_average = data.player_b_average

        self.db.commit()
        self._recalculate_elo_timeline(affected_players, updated_by, username)
        self.db.refresh(match)

        new_value = f'{{"date": "{match.date}", "score": "{match.player1_score}:{match.player2_score}", "winner_id": {match.winner_id}, "player_a": {match.player_a_id}, "player_b": {match.player_b_id}, "statistics": {{"180s_a": {match.player_a_180s}, "180s_b": {match.player_b_180s}, "high_finishes_a": {match.player_a_high_finishes}, "high_finishes_b": {match.player_b_high_finishes}, "low_darts_a": {match.player_a_low_darts}, "low_darts_b": {match.player_b_low_darts}, "average_a": {match.player_a_average}, "average_b": {match.player_b_average}}}}}'
        audit = AuditLog(user_id=updated_by, username=username, action="MATCH_UPDATED", entity_type="match", entity_id=match.id, old_value=old_value, new_value=new_value)
        self.db.add(audit)
        self.db.commit()
        return match

    def get_match(self, match_id: int) -> Match:
        """Get a match by ID."""
        match = self.match_repo.get_by_id(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail=f"Match with id {match_id} not found")
        return match

    def get_all_matches(self, from_date: date | None = None, to_date: date | None = None) -> list[Match]:
        """Get all matches, optionally filtered by date range."""
        return self.match_repo.get_all(from_date=from_date, to_date=to_date)

    def get_player_matches(self, player_id: int) -> list[Match]:
        """Get all matches for a specific player."""
        return self.match_repo.get_by_player(player_id)

    def delete_match(self, match_id: int, deleted_by: int | None = None, username: str | None = None) -> None:
        """Delete a match and recalculate the affected Elo timeline."""
        match = self.get_match(match_id)
        affected_players = {match.player_a_id, match.player_b_id}

        audit = AuditLog(
            user_id=deleted_by, username=username, action="MATCH_DELETED", entity_type="match",
            entity_id=match.id,
            old_value=f'{{"player_a": {match.player_a_id}, "player_b": {match.player_b_id}, "score": "{match.player1_score}:{match.player2_score}", "winner": {match.winner_id}, "date": "{match.date}"}}',
            new_value=None,
        )
        self.db.add(audit)
        self.db.commit()
        self.match_repo.delete(match)
        self._recalculate_elo_timeline(affected_players, deleted_by, username)

    def _recalculate_elo_timeline(
        self,
        affected_player_ids: set[int],
        user_id: int | None = None,
        username: str | None = None,
    ) -> int:
        """Recalculate the Elo timeline for all affected players.

        Boundary initialization (Fix #12):
        - Players directly involved in the changed match enter the window at
          their ``start_elo``. The window always starts at their earliest
          match, so their whole history lies inside the recalculation window.
        - Other players that appear inside the window enter at the Elo they
          had after their last match strictly before the window (or
          ``start_elo`` if they have no prior match). Pre-window ratings are
          preserved instead of being discarded.

        Returns:
            Number of matches recalculated.
        """
        if not affected_player_ids:
            return 0

        earliest_match = None
        for pid in affected_player_ids:
            player_matches = self.match_repo.get_by_player(pid)
            if player_matches:
                candidate = player_matches[0]
                if earliest_match is None or (
                    candidate.date, candidate.created_at, candidate.id
                ) < (earliest_match.date, earliest_match.created_at, earliest_match.id):
                    earliest_match = candidate

        if earliest_match is None:
            # All affected players have no remaining matches (e.g. their only
            # match was just deleted) -> reset them to the initial state.
            for pid in affected_player_ids:
                player = self.player_repo.get_by_id(pid)
                if player is not None:
                    player.current_elo = float(player.start_elo)
                    player.last_match_date = None
                    player.active = False
            self.db.commit()
            self._audit_recalculation(user_id, username, affected_player_ids, 0)
            return 0

        all_matches_from_start = self.match_repo.get_all()
        start_idx = 0
        for i, m in enumerate(all_matches_from_start):
            if m.id == earliest_match.id:
                start_idx = i
                break

        matches_to_recalc = all_matches_from_start[start_idx:]
        if not matches_to_recalc:
            return 0

        player_ids_in_timeline: set[int] = set()
        for m in matches_to_recalc:
            player_ids_in_timeline.add(m.player_a_id)
            player_ids_in_timeline.add(m.player_b_id)

        players: dict[int, Player] = {}
        for pid in player_ids_in_timeline:
            player = self.player_repo.get_by_id(pid)
            if player is None:
                continue

            if pid in affected_player_ids:
                # Directly affected player: their entire history is inside the
                # window, so the timeline starts at start_elo.
                player.current_elo = float(player.start_elo)
                player.last_match_date = None
            else:
                # In-window player with pre-window history: enter at the rating
                # from their last match strictly before the window.
                pre_window_match = self.match_repo.get_last_match_before(earliest_match, pid)
                if pre_window_match is not None:
                    player.current_elo = (
                        pre_window_match.elo_after_a
                        if pre_window_match.player_a_id == pid
                        else pre_window_match.elo_after_b
                    )
                    player.last_match_date = pre_window_match.date
                else:
                    player.current_elo = float(player.start_elo)
                    player.last_match_date = None

            players[pid] = player

        matches_to_recalc.sort(key=lambda m: (m.date, m.created_at, m.id))

        for m in matches_to_recalc:
            pa = players.get(m.player_a_id)
            pb = players.get(m.player_b_id)
            if pa is None or pb is None:
                continue

            winner_label = "A" if m.winner_id == m.player_a_id else "B"
            elo_result = calculate_match_elo(rating_a=pa.current_elo, rating_b=pb.current_elo, winner=winner_label, k_factor=m.k_factor)

            m.elo_before_a = pa.current_elo
            m.elo_before_b = pb.current_elo
            m.elo_after_a = elo_result.new_rating_a
            m.elo_after_b = elo_result.new_rating_b
            m.elo_change_a = elo_result.change_a
            m.elo_change_b = elo_result.change_b

            pa.current_elo = elo_result.new_rating_a
            pb.current_elo = elo_result.new_rating_b
            pa.last_match_date = m.date
            pb.last_match_date = m.date
            pa.active = True
            pb.active = True

        # Stale-rating edge case: an affected player whose matches were all
        # deleted is not part of the timeline, so reset it to the initial state.
        for pid in affected_player_ids:
            if pid in players:
                continue
            player = self.player_repo.get_by_id(pid)
            if player is not None:
                player.current_elo = float(player.start_elo)
                player.last_match_date = None
                player.active = False

        self.db.commit()
        self._audit_recalculation(
            user_id, username, affected_player_ids, len(matches_to_recalc)
        )
        return len(matches_to_recalc)

    def _audit_recalculation(
        self,
        user_id: int | None,
        username: str | None,
        affected_player_ids: set[int],
        matches_count: int,
    ) -> None:
        """Write a RANKING_RECALCULATED audit log entry."""
        audit = AuditLog(
            user_id=user_id, username=username,
            action="RANKING_RECALCULATED", entity_type="ranking", entity_id=None,
            old_value=None,
            new_value=f'{{"affected_players": {sorted(affected_player_ids)}, "matches_recalculated": {matches_count}}}',
        )
        self.db.add(audit)
        self.db.commit()

    def recalculate_all(self, user_id: int | None = None, username: str | None = None) -> dict:
        """Replay the complete Elo history from scratch for every player.

        Used for one-time data repair after a recalculation bugfix. Passes all
        players as affected, so the window starts at the very first match and
        every player enters at ``start_elo`` - identical to replaying the full
        history from scratch and canonicalizing all stored Elo snapshots.

        Returns:
            Dict with ``matches_recalculated`` and ``players_affected`` counts.
        """
        all_players = self.player_repo.get_all(include_disabled=True)
        all_player_ids = {p.id for p in all_players}
        matches_count = self._recalculate_elo_timeline(all_player_ids, user_id, username)
        return {
            "matches_recalculated": matches_count,
            "players_affected": len(all_player_ids),
        }
