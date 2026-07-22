"""Ranking service - generates rankings based on match history.

Rankings are generated for a selected period (From Date → To Date).
Default range is the current month.
"""

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.match import Match
from app.models.player import Player
from app.schemas.ranking import RankingEntry, RankingResponse


class RankingService:
    """Service layer for ranking generation."""

    def __init__(self, db: Session):
        self.db = db

    def generate_ranking(
        self,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        include_inactive: bool = False,
    ) -> RankingResponse:
        """Generate a ranking for the given date range.

        Args:
            from_date: Start of ranking period. Defaults to first day of current month.
            to_date: End of ranking period. Defaults to today.
            include_inactive: If True, include inactive players.

        Returns:
            RankingResponse with entries sorted by position.
        """
        if to_date is None:
            to_date = date.today()
        if from_date is None:
            from_date = date(to_date.year, to_date.month, 1)

        # Get eligible players
        players = self._get_eligible_players(include_inactive, to_date)

        # For each player, calculate:
        # - Elo at period start (Elo after the last match before from_date)
        # - Elo at period end (Elo after the last match on or before to_date)
        # - Elo change
        # - Position at period start and end
        entries: list[dict] = []

        for player in players:
            elo_at_start = self._get_elo_at_date(player, from_date, before=True)
            elo_at_end = self._get_elo_at_date(player, to_date, before=False)
            total_matches = self._get_total_match_count(player.id)

            entries.append({
                "player_id": player.id,
                "player_name": player.name,
                "elo_rating": elo_at_end,
                "elo_change": elo_at_end - elo_at_start,
                "start_elo": elo_at_start,
                "total_matches": total_matches,
            })

        # Sort by current Elo descending for end-of-period ranking
        entries.sort(key=lambda e: (-e["elo_rating"], e["player_name"]))

        # Assign positions and calculate position change
        # Calculate start-of-period positions
        start_entries = sorted(
            entries,
            key=lambda e: (-e["start_elo"], e["player_name"]),
        )
        start_positions: dict[int, int] = {}
        for i, e in enumerate(start_entries):
            start_positions[e["player_id"]] = i + 1

        ranking_entries: list[RankingEntry] = []
        for i, entry in enumerate(entries):
            end_position = i + 1
            start_position = start_positions.get(entry["player_id"], end_position)
            position_change = start_position - end_position  # positive = moved up

            ranking_entries.append(RankingEntry(
                player_id=entry["player_id"],
                player_name=entry["player_name"],
                position=end_position,
                elo_rating=entry["elo_rating"],
                elo_change=entry["elo_change"],
                position_change=position_change,
                total_matches=entry["total_matches"],
            ))

        return RankingResponse(
            from_date=from_date,
            to_date=to_date,
            entries=ranking_entries,
            generated_at=datetime.now(timezone.utc),
        )

    def _get_eligible_players(
        self, include_inactive: bool, as_of_date: date
    ) -> list[Player]:
        """Get players eligible for ranking.

        Args:
            include_inactive: If True, include inactive players.
            as_of_date: Date to check inactivity against.

        Returns:
            List of eligible players.
        """
        query = self.db.query(Player).filter(Player.disabled.is_(False))

        if not include_inactive:
            # Exclude inactive players (no match in last N months)
            inactivity_months = settings.inactivity_months
            cutoff_date = date(
                as_of_date.year - (inactivity_months // 12),
                as_of_date.month - (inactivity_months % 12),
                as_of_date.day,
            )
            # Handle month underflow
            if cutoff_date.month <= 0:
                cutoff_date = date(
                    cutoff_date.year - 1,
                    cutoff_date.month + 12,
                    cutoff_date.day,
                )

            query = query.filter(
                (Player.last_match_date >= cutoff_date)
                | (Player.last_match_date == None)  # noqa: E711
            )

        return query.all()

    def _get_elo_at_date(
        self, player: Player, target_date: date, before: bool = True
    ) -> float:
        """Get a player's Elo rating at a specific date.

        If before=True, returns Elo after the last match strictly before target_date.
        If before=False, returns Elo after the last match on or before target_date.

        If no matches found, returns player's start_elo.

        Args:
            player: The player.
            target_date: The date to look up.
            before: Whether to look before or up to the target date.

        Returns:
            The player's Elo at that point in time.
        """
        query = self.db.query(Match).filter(
            (Match.player_a_id == player.id) | (Match.player_b_id == player.id)
        )

        if before:
            query = query.filter(Match.date < target_date)
        else:
            query = query.filter(Match.date <= target_date)

        match = query.order_by(
            Match.date.desc(), Match.created_at.desc(), Match.id.desc()
        ).first()

        if match is None:
            return float(player.start_elo)

        if match.player_a_id == player.id:
            return match.elo_after_a
        return match.elo_after_b

    def _get_total_match_count(self, player_id: int) -> int:
        """Get the total lifetime match count for a player.

        Args:
            player_id: The player's ID.

        Returns:
            Total number of matches involving this player.
        """
        count = self.db.query(Match).filter(
            (Match.player_a_id == player_id) | (Match.player_b_id == player_id)
        ).count()
        return count

    def get_player_statistics(
        self,
        player_id: int,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> dict:
        """Get dart statistics for a player (period and all-time).

        Args:
            player_id: The player's ID.
            from_date: Start of period filter (None = no lower bound).
            to_date: End of period filter (None = no upper bound).

        Returns:
            Dict with 'period' and 'all_time' statistics.
        """
        # Get all matches for this player
        all_matches = self.db.query(Match).filter(
            (Match.player_a_id == player_id) | (Match.player_b_id == player_id)
        ).order_by(Match.date.asc(), Match.created_at.asc(), Match.id.asc()).all()

        if not all_matches:
            return {
                "player_id": player_id,
                "period": {"total_180s": 0, "high_finishes": [], "low_darts": []},
                "all_time": {"total_180s": 0, "high_finishes": [], "low_darts": []},
            }

        # Period matches
        period_matches = all_matches
        if from_date is not None:
            period_matches = [m for m in period_matches if m.date >= from_date]
        if to_date is not None:
            period_matches = [m for m in period_matches if m.date <= to_date]

        def _aggregate(matches: list[Match], pid: int) -> dict:
            total_180s = 0
            high_finishes: list[int] = []
            low_darts: list[int] = []
            for m in matches:
                if m.player_a_id == pid:
                    total_180s += m.player_a_180s or 0
                    if m.player_a_high_finishes:
                        high_finishes.extend(m.player_a_high_finishes)
                    if m.player_a_low_darts:
                        low_darts.extend(m.player_a_low_darts)
                else:
                    total_180s += m.player_b_180s or 0
                    if m.player_b_high_finishes:
                        high_finishes.extend(m.player_b_high_finishes)
                    if m.player_b_low_darts:
                        low_darts.extend(m.player_b_low_darts)
            return {
                "total_180s": total_180s,
                "high_finishes": sorted(high_finishes, reverse=True),
                "low_darts": sorted(low_darts),
            }

        return {
            "player_id": player_id,
            "period": _aggregate(period_matches, player_id),
            "all_time": _aggregate(all_matches, player_id),
        }
