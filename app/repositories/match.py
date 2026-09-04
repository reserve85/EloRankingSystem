"""Match repository for database access.

Mutation methods (create/update/delete) only flush the session so that
auto-generated IDs are available; they never commit. The service layer owns
the transaction boundary and commits once at the end of a logical operation
(Fix #7).
"""

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
        return query.order_by(Match.date.asc(), Match.created_at.asc(), Match.id.asc()).all()

    def get_by_player(self, player_id: int) -> list[Match]:
        """Get all matches involving a specific player."""
        return (
            self.db.query(Match)
            .filter((Match.player_a_id == player_id) | (Match.player_b_id == player_id))
            .order_by(Match.date.asc(), Match.created_at.asc(), Match.id.asc())
            .all()
        )

    def get_last_match_before(self, match: Match, player_id: int) -> Optional[Match]:
        """Get the player's most recent match strictly before the given match.

        Uses the deterministic timeline order ``(date ASC, created_at ASC, id ASC)``
        and returns None if the player has no prior match.

        The comparison is intentionally done in Python against loaded ORM values
        instead of a SQL ``tuple_()`` row-value comparison: SQLite stores
        ``created_at`` via ``func.now()`` with second precision while SQLAlchemy
        binds datetime parameters with microsecond precision, which breaks
        string row-value comparisons for matches created within the same second.

        Args:
            match: The boundary match; the returned match is strictly before it.
            player_id: The player whose history is queried.

        Returns:
            The most recent prior match involving the player, or None.
        """
        boundary = (match.date, match.created_at, match.id)
        last_prior: Optional[Match] = None
        for m in self.get_by_player(player_id):
            if (m.date, m.created_at, m.id) < boundary:
                last_prior = m
            else:
                break
        return last_prior

    def get_from_match(self, match: Match) -> list[Match]:
        """Get all matches at or after the given boundary match's timeline position.

        Returns matches where (date, created_at, id) >= (match.date, match.created_at,
        match.id), ordered date ASC, created_at ASC, id ASC — identical set and order to
        ``get_all()[i:]`` where ``i`` is the boundary match's index.

        The boundary is split into two parts deliberately:
          1. a SQL ``date >= match.date`` pre-filter (indexed, cheap), then
          2. a Python tuple comparison on the loaded same-day rows.

        A single SQL row-value comparison ``tuple_(date, created_at, id) >= (...)``
        is intentionally avoided: ``created_at`` is written by ``func.now()`` at *second*
        precision while SQLAlchemy binds datetimes at *microsecond* precision, which
        breaks string row-value comparisons on SQLite for matches created within the
        same second (same precision pitfall as ``get_last_match_before``).
        """
        boundary = (match.date, match.created_at, match.id)
        return [
            m
            for m in self.db.query(Match)
            .filter(Match.date >= match.date)
            .order_by(Match.date.asc(), Match.created_at.asc(), Match.id.asc())
            .all()
            if (m.date, m.created_at, m.id) >= boundary
        ]

    def create(self, match: Match) -> Match:
        """Create a new match."""
        self.db.add(match)
        self.db.flush()
        self.db.refresh(match)
        return match

    def update(self, match: Match) -> Match:
        """Update an existing match."""
        self.db.flush()
        self.db.refresh(match)
        return match

    def delete(self, match: Match) -> None:
        """Delete a match."""
        self.db.delete(match)
        self.db.flush()

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
                (
                    (Match.player_a_id == player_a_id)
                    & (Match.player_b_id == player_b_id)
                    & (Match.player1_score == player1_score)
                    & (Match.player2_score == player2_score)
                )
                |
                # Reversed order + reversed scores
                (
                    (Match.player_a_id == player_b_id)
                    & (Match.player_b_id == player_a_id)
                    & (Match.player1_score == player2_score)
                    & (Match.player2_score == player1_score)
                )
            ),
        )
        if exclude_match_id is not None:
            query = query.filter(Match.id != exclude_match_id)
        return query.first()
