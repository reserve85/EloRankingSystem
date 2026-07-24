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

    def create_match(self, data: MatchCreate, created_by: int | None = None) -> Match:
        """Create a new match using Best-of-5 scores, then recalculate."""
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
            player_a_180s=data.player_a_180s,
            player_b_180s=data.player_b_180s,
            player_a_high_finishes=data.player_a_high_finishes,
            player_b_high_finishes=data.player_b_high_finishes,
            player_a_low_darts=data.player_a_low_darts,
            player_b_low_darts=data.player_b_low_darts,
            created_by=created_by,
        )
        match = self.match_repo.create(match)

        self._recalculate_elo_timeline({data.player_a_id, data.player_b_id})
        self.db.refresh(match)

        audit = AuditLog(
            user_id=created_by, action="MATCH_CREATED", entity_type="match",
            entity_id=match.id, old_value=None,
            new_value=f'{{"player_a": {data.player_a_id}, "player_b": {data.player_b_id}, "score": "{data.player1_score}:{data.player2_score}", "winner": {winner_id}, "date": "{data.date}", "statistics": {{"180s_a": {data.player_a_180s}, "180s_b": {data.player_b_180s}, "high_finishes_a": {data.player_a_high_finishes}, "high_finishes_b": {data.player_b_high_finishes}, "low_darts_a": {data.player_a_low_darts}, "low_darts_b": {data.player_b_low_darts}}}}}',
        )
        self.db.add(audit)
        self.db.commit()
        return match

    def update_match(self, match_id: int, data: MatchUpdate, updated_by: int | None = None) -> Match:
        """Update a match and recalculate the affected Elo timeline."""
        match = self.get_match(match_id)
        old_value = f'{{"date": "{match.date}", "score": "{match.player1_score}:{match.player2_score}", "winner_id": {match.winner_id}, "player_a": {match.player_a_id}, "player_b": {match.player_b_id}, "statistics": {{"180s_a": {match.player_a_180s}, "180s_b": {match.player_b_180s}, "high_finishes_a": {match.player_a_high_finishes}, "high_finishes_b": {match.player_b_high_finishes}, "low_darts_a": {match.player_a_low_darts}, "low_darts_b": {match.player_b_low_darts}}}}}'
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

        self.db.commit()
        self._recalculate_elo_timeline(affected_players)
        self.db.refresh(match)

        new_value = f'{{"date": "{match.date}", "score": "{match.player1_score}:{match.player2_score}", "winner_id": {match.winner_id}, "player_a": {match.player_a_id}, "player_b": {match.player_b_id}, "statistics": {{"180s_a": {match.player_a_180s}, "180s_b": {match.player_b_180s}, "high_finishes_a": {match.player_a_high_finishes}, "high_finishes_b": {match.player_b_high_finishes}, "low_darts_a": {match.player_a_low_darts}, "low_darts_b": {match.player_b_low_darts}}}}}'
        audit = AuditLog(user_id=updated_by, action="MATCH_UPDATED", entity_type="match", entity_id=match.id, old_value=old_value, new_value=new_value)
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

    def delete_match(self, match_id: int, deleted_by: int | None = None) -> None:
        """Delete a match and recalculate the affected Elo timeline."""
        match = self.get_match(match_id)
        affected_players = {match.player_a_id, match.player_b_id}

        audit = AuditLog(
            user_id=deleted_by, action="MATCH_DELETED", entity_type="match",
            entity_id=match.id,
            old_value=f'{{"player_a": {match.player_a_id}, "player_b": {match.player_b_id}, "score": "{match.player1_score}:{match.player2_score}", "winner": {match.winner_id}, "date": "{match.date}"}}',
            new_value=None,
        )
        self.db.add(audit)
        self.db.commit()
        self.match_repo.delete(match)
        self._recalculate_elo_timeline(affected_players)

    def _recalculate_elo_timeline(self, affected_player_ids: set[int]) -> None:
        """Recalculate the Elo timeline for all affected players."""
        if not affected_player_ids:
            return

        earliest_match = None
        for pid in affected_player_ids:
            player_matches = self.match_repo.get_by_player(pid)
            if player_matches:
                candidate = player_matches[0]
                if earliest_match is None or (candidate.date, candidate.created_at, candidate.id) < (earliest_match.date, earliest_match.created_at, earliest_match.id):
                    earliest_match = candidate

        if earliest_match is None:
            for pid in affected_player_ids:
                player = self.player_repo.get_by_id(pid)
                if player is not None:
                    player.current_elo = float(player.start_elo)
                    player.last_match_date = None
                    player.active = False
            self.db.commit()
            return

        all_matches_from_start = self.match_repo.get_all()
        start_idx = 0
        for i, m in enumerate(all_matches_from_start):
            if m.id == earliest_match.id:
                start_idx = i
                break

        matches_to_recalc = all_matches_from_start[start_idx:]
        if not matches_to_recalc:
            return

        player_ids_in_timeline: set[int] = set()
        for m in matches_to_recalc:
            player_ids_in_timeline.add(m.player_a_id)
            player_ids_in_timeline.add(m.player_b_id)

        players: dict[int, Player] = {}
        for pid in player_ids_in_timeline:
            player = self.player_repo.get_by_id(pid)
            if player is not None:
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
            elo_result = calculate_match_elo(rating_a=pa.current_elo, rating_b=pb.current_elo, winner=winner_label)

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

        self.db.commit()

        audit = AuditLog(
            action="RANKING_RECALCULATED", entity_type="ranking", entity_id=None,
            old_value=None,
            new_value=f'{{"affected_players": {list(affected_player_ids)}, "matches_recalculated": {len(matches_to_recalc)}}}',
        )
        self.db.add(audit)
        self.db.commit()
