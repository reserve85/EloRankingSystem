"""Ranking service - generates rankings based on match history.

Rankings are generated for a selected period (From Date → To Date).
Default range is the current month.
"""

import calendar
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
            stats = self._get_period_statistics(player.id, from_date, to_date)

            entries.append({
                "player_id": player.id,
                "player_name": player.name,
                "elo_rating": elo_at_end,
                "elo_change": elo_at_end - elo_at_start,
                "start_elo": elo_at_start,
                "total_matches": total_matches,
                "total_180s": stats["total_180s"],
                "high_finishes": stats["high_finishes"],
                "low_darts": stats["low_darts"],
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
                total_180s=entry["total_180s"],
                high_finishes=entry["high_finishes"],
                low_darts=entry["low_darts"],
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
            cutoff_year = as_of_date.year
            cutoff_month = as_of_date.month - inactivity_months
            while cutoff_month <= 0:
                cutoff_month += 12
                cutoff_year -= 1
            max_day = calendar.monthrange(cutoff_year, cutoff_month)[1]
            cutoff_day = min(as_of_date.day, max_day)
            cutoff_date = date(cutoff_year, cutoff_month, cutoff_day)

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

    def _get_period_statistics(
        self, player_id: int, from_date: date, to_date: date
    ) -> dict:
        """Get dart statistics for a player within a period.

        Args:
            player_id: The player's ID.
            from_date: Start of period.
            to_date: End of period.

        Returns:
            Dict with total_180s, high_finishes, low_darts.
        """
        matches = self.db.query(Match).filter(
            ((Match.player_a_id == player_id) | (Match.player_b_id == player_id))
            & (Match.date >= from_date)
            & (Match.date <= to_date)
        ).all()

        total_180s = 0
        high_finishes: list[int] = []
        low_darts: list[int] = []
        for m in matches:
            if m.player_a_id == player_id:
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

    def get_elo_history(self, player_id: int) -> list[dict]:
        """Get Elo history for a player (all matches with Elo after each).

        Args:
            player_id: The player's ID.

        Returns:
            List of dicts with date, elo, match_id.
        """
        matches = self.db.query(Match).filter(
            (Match.player_a_id == player_id) | (Match.player_b_id == player_id)
        ).order_by(Match.date.asc(), Match.created_at.asc(), Match.id.asc()).all()

        history = []
        for m in matches:
            elo = m.elo_after_a if m.player_a_id == player_id else m.elo_after_b
            history.append({
                "date": m.date.isoformat(),
                "elo": elo,
                "match_id": m.id,
            })
        return history

    def get_all_time_high_elo(self, player_id: int) -> dict:
        """Get the highest Elo rating ever reached by a player.

        Args:
            player_id: The player's ID.

        Returns:
            Dict with max_elo and date_reached.
        """
        player = self.db.query(Player).filter(Player.id == player_id).first()
        if player is None:
            return {"max_elo": 0, "date_reached": None}

        matches = self.db.query(Match).filter(
            (Match.player_a_id == player_id) | (Match.player_b_id == player_id)
        ).order_by(Match.date.asc(), Match.created_at.asc(), Match.id.asc()).all()

        if not matches:
            return {"max_elo": float(player.start_elo), "date_reached": None}

        max_elo = float(player.start_elo)
        max_date = None
        for m in matches:
            elo = m.elo_after_a if m.player_a_id == player_id else m.elo_after_b
            if elo > max_elo:
                max_elo = elo
                max_date = m.date.isoformat()

        return {"max_elo": max_elo, "date_reached": max_date}

    def get_all_players_all_time_high_elo(self, include_inactive: bool = False) -> list[dict]:
        """Get the highest Elo rating ever reached for all players.

        Only includes players with at least 1 match (ignores players with 0 games).

        Args:
            include_inactive: If True, include inactive players.

        Returns:
            List of dicts with player_id, player_name, max_elo, date_reached, inactive.
        """
        players = self.db.query(Player).filter(Player.disabled.is_(False)).all()

        if not include_inactive:
            # Filter out inactive players
            inactivity_months = settings.inactivity_months
            today = date.today()
            cutoff_year = today.year
            cutoff_month = today.month - inactivity_months
            while cutoff_month <= 0:
                cutoff_month += 12
                cutoff_year -= 1
            max_day = calendar.monthrange(cutoff_year, cutoff_month)[1]
            cutoff_day = min(today.day, max_day)
            cutoff_date = date(cutoff_year, cutoff_month, cutoff_day)
            active_players = []
            for p in players:
                if p.last_match_date is None:
                    # Player with no matches - check if they have any matches at all
                    has_match = self.db.query(Match).filter(
                        (Match.player_a_id == p.id) | (Match.player_b_id == p.id)
                    ).first()
                    if has_match is None:
                        continue  # Skip players with 0 games
                    # Player with matches but no last_match_date -> inactive
                elif p.last_match_date >= cutoff_date:
                    active_players.append(p)
                # else: inactive player, skip
            # Only include active players when not including inactive
            players = active_players
        else:
            # When including inactive, still filter out players with 0 games
            players_with_games = []
            for p in players:
                has_match = self.db.query(Match).filter(
                    (Match.player_a_id == p.id) | (Match.player_b_id == p.id)
                ).first()
                if has_match is None:
                    continue  # Skip players with 0 games
                players_with_games.append(p)
            players = players_with_games

        result = []
        for player in players:
            ath = self.get_all_time_high_elo(player.id)
            # Determine if player is inactive
            is_inactive = False
            if player.last_match_date is None:
                is_inactive = True
            else:
                inactivity_months = settings.inactivity_months
                today = date.today()
                cutoff_year = today.year
                cutoff_month = today.month - inactivity_months
                while cutoff_month <= 0:
                    cutoff_month += 12
                    cutoff_year -= 1
                max_day = calendar.monthrange(cutoff_year, cutoff_month)[1]
                cutoff_day = min(today.day, max_day)
                cutoff_date = date(cutoff_year, cutoff_month, cutoff_day)
                if player.last_match_date < cutoff_date:
                    is_inactive = True

            result.append({
                "player_id": player.id,
                "player_name": player.name,
                "max_elo": ath["max_elo"],
                "date_reached": ath["date_reached"],
                "inactive": is_inactive,
            })

        # Sort by max_elo descending
        result.sort(key=lambda x: (-x["max_elo"], x["player_name"]))
        return result

    def get_all_time_high_ranking(self, player_id: int) -> dict:
        """Get the best ranking position ever achieved by a player.

        Considers all players (including inactive) at each match date.

        Args:
            player_id: The player's ID.

        Returns:
            Dict with best_rank and date_reached.
        """
        matches = self.db.query(Match).filter(
            (Match.player_a_id == player_id) | (Match.player_b_id == player_id)
        ).order_by(Match.date.asc(), Match.created_at.asc(), Match.id.asc()).all()

        if not matches:
            return {"best_rank": None, "date_reached": None}

        best_rank = None
        best_date = None

        for m in matches:
            # Get all players' Elo at this match date
            all_players = self.db.query(Player).filter(Player.disabled.is_(False)).all()
            player_elos = []
            for p in all_players:
                elo = self._get_elo_at_date(p, m.date, before=False)
                # Only include players with at least 1 match on or before this date
                has_match = self.db.query(Match).filter(
                    ((Match.player_a_id == p.id) | (Match.player_b_id == p.id))
                    & (Match.date <= m.date)
                ).first()
                if has_match:
                    player_elos.append((p.id, elo))

            player_elos.sort(key=lambda x: (-x[1], x[0]))
            for rank, (pid, _) in enumerate(player_elos, 1):
                if pid == player_id:
                    if best_rank is None or rank < best_rank:
                        best_rank = rank
                        best_date = m.date.isoformat()
                    break

        return {"best_rank": best_rank, "date_reached": best_date}
