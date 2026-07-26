"""Match repository for database access."""

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.match import Match


class MatchRepository:
    """Repository for match database operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, match_id: int) -> Optional[Match]:
        """Get a match by ID."""
        return self.db.query(Match).filter(Match.id == match_id).first()

    def get_all(
        self,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> list[Match]:
        """Get all matches, optionally filtered by date range."""
        query = self.db.query(Match)
        if from_date is not None:
            query = query.filter(Match.date >= from_date)
        if to_date is not None:
            query = query.filter(Match.date <= to_date)
        return query.order_by(
            Match.date.asc(), Match.created_at.asc(), Match.id.asc()
        ).all()

    def get_by_player(self, player_id: int) -> list[Match]:
        """Get all matches involving a specific player."""
        return (
            self.db.query(Match)
            .filter(
                (Match.player_a_id == player_id) | (Match.player_b_id == player_id)
            )
            .order_by(Match.date.asc(), Match.created_at.asc(), Match.id.asc())
            .all()
        )

    def create(self, match: Match) -> Match:
        """Create a new match."""
        self.db.add(match)
        self.db.commit()
        self.db.refresh(match)
        return match

    def update(self, match: Match) -> Match:
        """Update an existing match."""
        self.db.commit()
        self.db.refresh(match)
        return match

    def delete(self, match: Match) -> None:
        """Delete a match."""
        self.db.delete(match)
        self.db.commit()

    def get_duplicate_match(
        self,
        player_a_id: int,
        player_b_id: int,
        player1_score: int,
        player2_score: int,
        match_date: date,
        exclude_match_id: Optional[int] = None,
    ) -> Optional[Match]:
        """Find a duplicate match with same players, exact score, and date.

        Args:
            player_a_id: ID of player A
            player_b_id: ID of player B
            player1_score: Score of player A
            player2_score: Score of player B
            match_date: Date of the match
            exclude_match_id: Optional match ID to exclude from search (for updates)

        Returns:
            Duplicate match if found, None otherwise.
        """
        # Check for same players with exact same score on same date
        query = self.db.query(Match).filter(
            Match.date == match_date,
            and_(
                # Same order + same scores
                ((Match.player_a_id == player_a_id) & (Match.player_b_id == player_b_id) &
                 (Match.player1_score == player1_score) & (Match.player2_score == player2_score)) |
                # Reversed order + reversed scores
                ((Match.player_a_id == player_b_id) & (Match.player_b_id == player_a_id) &
                 (Match.player1_score == player2_score) & (Match.player2_score == player1_score))
            )
        )
        if exclude_match_id is not None:
            query = query.filter(Match.id != exclude_match_id)
        return query.first()
