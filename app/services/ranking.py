"""Ranking service - generates rankings based on match history.

Rankings are generated for a selected period (From Date → To Date).
Default range is the current month.
"""

import calendar
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.match import Match
from app.models.player import Player
from app.schemas.ranking import RankingEntry, RankingResponse


def _validate_date_range(from_date: Optional[date], to_date: Optional[date]) -> None:
    """Reject an inverted ``from_date`` > ``to_date`` range (review #3).

    Callers resolve defaults first, so both values are normally set. Without
    this check the ranking, statistics and PDF-report endpoints silently
    returned empty or misleading output for an inverted range; now they answer
    422 instead. The UI already guards against this for its own inputs.
    """
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(
            status_code=422,
            detail=f"from_date ({from_date.isoformat()}) cannot be after to_date "
            f"({to_date.isoformat()})",
        )


class RankingService:
    """Service layer for ranking generation."""

    def __init__(self, db: Session):
        self.db = db

    # Disabled players remain a permanent part of the ranking field. They are
    # simply not allowed to play new matches (the match service layer rejects
    # them), and the UI renders their names struck out. Disabling therefore
    # never shrinks the total ranking denominator, so it cannot inflate any
    # position statistic (Best Rank, ranking positions, position changes) -
    # live or historical. The ``PlayerDisablePeriod`` rows written by the
    # player service are kept purely as an audit trail of when someone was
    # disabled.
    #
    # The lists follow the same "include inactive / disabled" checkbox: when
    # it is unticked, both inactive and disabled players are hidden from the
    # shown table; when ticked, both appear (labelled ``(inactive)`` /
    # ``(disabled)``). The underlying statistics always use the full field.

    @staticmethod
    def _inactive_cutoff(as_of_date: date) -> date:
        """Cutoff date for inactivity: ``inactivity_months`` before ``as_of_date``."""
        inactivity_months = settings.inactivity_months
        cutoff_year = as_of_date.year
        cutoff_month = as_of_date.month - inactivity_months
        while cutoff_month <= 0:
            cutoff_month += 12
            cutoff_year -= 1
        max_day = calendar.monthrange(cutoff_year, cutoff_month)[1]
        cutoff_day = min(as_of_date.day, max_day)
        return date(cutoff_year, cutoff_month, cutoff_day)

    @staticmethod
    def _is_inactive(player: Player, as_of_date: date) -> bool:
        """Whether ``player`` counts as inactive at ``as_of_date``.

        A player is inactive when they have never played or their last match
        is older than ``settings.inactivity_months``.
        """
        if player.last_match_date is None:
            return True
        return player.last_match_date < RankingService._inactive_cutoff(as_of_date)

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
            include_inactive: If True, also include inactive and disabled players.

        Returns:
            RankingResponse with entries sorted by position.
        """
        if to_date is None:
            to_date = date.today()
        if from_date is None:
            from_date = date(to_date.year, to_date.month, 1)

        _validate_date_range(from_date, to_date)

        # Get eligible players
        players = self._get_eligible_players(include_inactive, to_date, from_date)

        # For each player, calculate:
        # - Elo at period start (Elo after the last match before from_date)
        # - Elo at period end (Elo after the last match on or before to_date)
        # - Elo change
        # - Position at period start and end
        # All per-player values are derived from a single batched query instead
        # of the previous three queries per player (Fix #8: N+1 → 1). The
        # values are identical to the old per-player queries, so the ranking
        # positions never change.
        records = self._build_ranking_records(from_date, to_date)
        entries: list[dict] = []

        # Players with at least one match up to ``to_date`` have a real ranking
        # position; everyone else (e.g. a brand-new member without any matches)
        # has no previous position at all. The old code computed a phantom
        # position change for those players by comparing two synthetic
        # start_elo-derived positions (Fix #1).
        players_with_matches = set(records.keys())

        for player in players:
            is_inactive = RankingService._is_inactive(player, to_date)
            rec = records.get(player.id)
            if rec is None:
                # No matches up to to_date -> start_elo at both boundaries.
                elo_at_start = float(player.start_elo)
                elo_at_end = float(player.start_elo)
                total_matches = 0
                total_180s = 0
                high_finishes: list[int] = []
                low_darts: list[int] = []
            else:
                elo_at_start = (
                    rec["elo_at_start"]
                    if rec["elo_at_start"] is not None
                    else float(player.start_elo)
                )
                elo_at_end = rec["elo_at_end"]
                total_matches = rec["match_count"]
                total_180s = rec["total_180s"]
                high_finishes = sorted(rec["high_finishes"], reverse=True)
                low_darts = sorted(rec["low_darts"])

            entries.append(
                {
                    "player_id": player.id,
                    "player_name": player.name,
                    "disabled": player.disabled,
                    "inactive": is_inactive,
                    "elo_rating": elo_at_end,
                    "elo_change": elo_at_end - elo_at_start,
                    "start_elo": elo_at_start,
                    "total_matches": total_matches,
                    "total_180s": total_180s,
                    "high_finishes": high_finishes,
                    "low_darts": low_darts,
                }
            )

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
            if entry["player_id"] not in players_with_matches:
                # Fix #1: no match history up to to_date -> the player has no
                # previous ranking position, so a rank change would be
                # fabricated. Show '-' (None) instead.
                position_change = None
            else:
                start_position = start_positions.get(entry["player_id"], end_position)
                position_change = start_position - end_position  # positive = moved up

            ranking_entries.append(
                RankingEntry(
                    player_id=entry["player_id"],
                    player_name=entry["player_name"],
                    disabled=entry["disabled"],
                    inactive=entry["inactive"],
                    position=end_position,
                    elo_rating=entry["elo_rating"],
                    elo_change=entry["elo_change"],
                    position_change=position_change,
                    total_matches=entry["total_matches"],
                    total_180s=entry["total_180s"],
                    high_finishes=entry["high_finishes"],
                    low_darts=entry["low_darts"],
                )
            )

        return RankingResponse(
            from_date=from_date,
            to_date=to_date,
            entries=ranking_entries,
            generated_at=datetime.now(timezone.utc),
        )

    def _get_eligible_players(
        self,
        include_inactive: bool,
        as_of_date: date,
        from_date: Optional[date] = None,
    ) -> list[Player]:
        """Get players eligible for ranking.

        If include_inactive is False, only players with at least 1 match
        in the selected date interval or flagged active are included - and
        disabled players are hidden like inactive ones, because the lists
        follow the same "include inactive / disabled" toggle.

        Args:
            include_inactive: If True, also include inactive and disabled
                players.
            as_of_date: Date to check inactivity against.
            from_date: Starting from interval for activity check.

        Returns:
            List of eligible players.
        """
        query = self.db.query(Player)

        # Fix #3 II (replaces Fix #2/#4 heuristics): a player is a competitor
        # from their explicit entry date (member-since) onwards
        # (rule: entry_date <= selected_period_end). Every player
        # entered by a date counts on that date - disabled players included -
        # ranked by their Elo as of that date, whether or not they had played
        # by then. Adding one day
        # turns the inclusive date comparison into a portable datetime
        # comparison (SQLite / PostgreSQL / MySQL) for the created_at
        # fallback (legacy rows with a NULL entry_date).
        from sqlalchemy import or_

        entry_cutoff = datetime.combine(as_of_date, time.min) + timedelta(days=1)
        has_entry_date = (Player.entry_date.isnot(None)) & (Player.entry_date <= as_of_date)
        legacy_fallback = (Player.entry_date.is_(None)) & (Player.created_at < entry_cutoff)
        query = query.filter(or_(has_entry_date, legacy_fallback))

        if not include_inactive:
            # Include players who had a match in the interval OR who played
            # recently (within the inactivity window). The ``active`` DB flag
            # is deliberately NOT used here: it is a legacy "ever played"
            # flag, so players who last matched months ago would otherwise
            # leak back into the table even though they are inactive - the
            # same rule that labels them ``(inactive)`` must also hide them.
            interval_start = from_date or as_of_date
            active_player_ids = (
                self.db.query(Match.player_a_id)
                .filter(Match.date >= interval_start, Match.date <= as_of_date)
                .union(
                    self.db.query(Match.player_b_id).filter(
                        Match.date >= interval_start, Match.date <= as_of_date
                    )
                )
                .distinct()
                .subquery()
            )
            cutoff = RankingService._inactive_cutoff(as_of_date)
            played_recently = (Player.last_match_date.isnot(None)) & (
                Player.last_match_date >= cutoff
            )

            query = query.filter(
                or_(
                    Player.id.in_(active_player_ids.select()),
                    played_recently,
                )
            )
            # Disabled players are hidden from the table unless the "include
            # inactive / disabled" flag is set (they follow ``include_inactive``).
            query = query.filter(Player.disabled.is_(False))

        return query.all()

    def _build_ranking_records(self, from_date: date, to_date: date) -> dict[int, dict]:
        """Batch-load matches up to ``to_date`` and aggregate per player.

        Fix #8: replaces the previous N+1 pattern (three per-player queries
        in ``generate_ranking``) with a single query plus in-memory
        aggregation. The values are identical to the old per-player queries:

        - ``elo_at_end`` = the player's stored ``elo_after`` for the last
          match with ``date <= to_date``.
        - ``elo_at_start`` = the stored ``elo_after`` for the last match
          with ``date < from_date`` (None when the player has no prior match).
        - period statistics aggregate matches with
          ``from_date <= date <= to_date``.

        Matches are iterated in the deterministic timeline order
        (date ASC, created_at ASC, id ASC), so the last value written for a
        player is exactly the match the old ``ORDER BY date DESC,
        created_at DESC, id DESC LIMIT 1`` queries returned - ranking
        positions are therefore unchanged.

        Args:
            from_date: Start of the ranking period.
            to_date: End of the ranking period.

        Returns:
            Dict mapping ``player_id`` to an aggregation record.

        Performance note (Tier 0 tripwire): this is still a full table scan
        (``Match.date <= to_date``) on every call - fine for club-scale
        histories (a few thousand matches). ``TestBulkScaleGuard`` in
        tests/test_ranking_optimization.py pins an upper bound on runtime and
        SELECT count so a gross regression (e.g. a reintroduced N+1) fails CI
        instead of silently degrading. If a much larger dataset ever shows up,
        materialize the per-player values on write (inside
        ``recalculate_elo_timeline``) instead of per-request scans.
        """
        matches = (
            self.db.query(Match)
            .filter(Match.date <= to_date)
            .order_by(Match.date.asc(), Match.created_at.asc(), Match.id.asc())
            .all()
        )

        records: dict[int, dict] = {}
        for m in matches:
            for pid, elo_after in (
                (m.player_a_id, m.elo_after_a),
                (m.player_b_id, m.elo_after_b),
            ):
                rec = records.setdefault(
                    pid,
                    {
                        "elo_at_start": None,  # elo_after of last match before from_date
                        "elo_at_end": None,  # elo_after of last match up to to_date
                        "match_count": 0,
                        "total_180s": 0,
                        "high_finishes": [],
                        "low_darts": [],
                    },
                )
                rec["elo_at_end"] = elo_after
                if m.date < from_date:
                    rec["elo_at_start"] = elo_after
                    continue

                # Match inside the period: aggregate dart statistics.
                rec["match_count"] += 1
                if m.player_a_id == pid:
                    rec["total_180s"] += m.player_a_180s or 0
                    if m.player_a_high_finishes:
                        rec["high_finishes"].extend(m.player_a_high_finishes)
                    if m.player_a_low_darts:
                        rec["low_darts"].extend(m.player_a_low_darts)
                else:
                    rec["total_180s"] += m.player_b_180s or 0
                    if m.player_b_high_finishes:
                        rec["high_finishes"].extend(m.player_b_high_finishes)
                    if m.player_b_low_darts:
                        rec["low_darts"].extend(m.player_b_low_darts)

        return records

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
        _validate_date_range(from_date, to_date)

        # Get all matches for this player
        all_matches = (
            self.db.query(Match)
            .filter((Match.player_a_id == player_id) | (Match.player_b_id == player_id))
            .order_by(Match.date.asc(), Match.created_at.asc(), Match.id.asc())
            .all()
        )

        if not all_matches:
            empty = {
                "total_matches": 0,
                "wins": 0,
                "losses": 0,
                "legs_won": 0,
                "legs_lost": 0,
                "total_180s": 0,
                "high_finishes": [],
                "low_darts": [],
                "average": None,
                "average_count": 0,
            }
            return {
                "player_id": player_id,
                "period": dict(empty),
                "all_time": dict(empty, average_last100=None),
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
            wins = 0
            losses = 0
            legs_won = 0
            legs_lost = 0
            averages: list[float] = []
            for m in matches:
                is_a = m.player_a_id == pid
                if is_a:
                    total_180s += m.player_a_180s or 0
                    if m.player_a_high_finishes:
                        high_finishes.extend(m.player_a_high_finishes)
                    if m.player_a_low_darts:
                        low_darts.extend(m.player_a_low_darts)
                    if m.player_a_average is not None:
                        averages.append(m.player_a_average)
                else:
                    total_180s += m.player_b_180s or 0
                    if m.player_b_high_finishes:
                        high_finishes.extend(m.player_b_high_finishes)
                    if m.player_b_low_darts:
                        low_darts.extend(m.player_b_low_darts)
                    if m.player_b_average is not None:
                        averages.append(m.player_b_average)
                my_score = m.player1_score if is_a else m.player2_score
                opp_score = m.player2_score if is_a else m.player1_score
                legs_won += my_score or 0
                legs_lost += opp_score or 0
                if m.winner_id == pid:
                    wins += 1
                else:
                    losses += 1
            avg_val = round(sum(averages) / len(averages), 2) if averages else None
            return {
                "total_matches": len(matches),
                "wins": wins,
                "losses": losses,
                "legs_won": legs_won,
                "legs_lost": legs_lost,
                "total_180s": total_180s,
                "high_finishes": sorted(high_finishes, reverse=True),
                "low_darts": sorted(low_darts),
                "average": avg_val,
                "average_count": len(averages),
            }

        all_time_result = _aggregate(all_matches, player_id)
        # Compute last-100 average from the most recent matches with averages
        all_time_averages: list[float] = []
        for m in reversed(all_matches):
            is_a = m.player_a_id == player_id
            avg = m.player_a_average if is_a else m.player_b_average
            if avg is not None:
                all_time_averages.append(avg)
            if len(all_time_averages) >= 100:
                break
        avg_last100 = (
            round(sum(all_time_averages) / len(all_time_averages), 2) if all_time_averages else None
        )
        all_time_result["average_last100"] = avg_last100

        return {
            "player_id": player_id,
            "period": _aggregate(period_matches, player_id),
            "all_time": all_time_result,
        }

    def get_average_history(self, player_id: int) -> list[dict]:
        """Get average history for a player (matches with a recorded average).

        Args:
            player_id: The player's ID.

        Returns:
            List of dicts with date, average, match_id.
        """
        matches = (
            self.db.query(Match)
            .filter((Match.player_a_id == player_id) | (Match.player_b_id == player_id))
            .order_by(Match.date.asc(), Match.created_at.asc(), Match.id.asc())
            .all()
        )

        history = []
        for m in matches:
            avg = m.player_a_average if m.player_a_id == player_id else m.player_b_average
            if avg is not None:
                history.append(
                    {
                        "date": m.date.isoformat(),
                        "average": avg,
                        "match_id": m.id,
                    }
                )
        return history

    def get_elo_history(self, player_id: int) -> list[dict]:
        """Get Elo history for a player (all matches with Elo after each).

        Args:
            player_id: The player's ID.

        Returns:
            List of dicts with date, elo, match_id.
        """
        matches = (
            self.db.query(Match)
            .filter((Match.player_a_id == player_id) | (Match.player_b_id == player_id))
            .order_by(Match.date.asc(), Match.created_at.asc(), Match.id.asc())
            .all()
        )

        history = []
        for m in matches:
            elo = m.elo_after_a if m.player_a_id == player_id else m.elo_after_b
            history.append(
                {
                    "date": m.date.isoformat(),
                    "elo": elo,
                    "match_id": m.id,
                }
            )
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

        matches = (
            self.db.query(Match)
            .filter((Match.player_a_id == player_id) | (Match.player_b_id == player_id))
            .order_by(Match.date.asc(), Match.created_at.asc(), Match.id.asc())
            .all()
        )

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

        Includes every player except inactive/disabled ones when the flag is
        off (disabled players are flagged ``disabled``), even those with 0
        matches (shows start_elo). Optimized: loads all matches in a single
        query and computes ATH in memory.

        Args:
            include_inactive: If True, also include inactive and disabled
                players.

        Returns:
            List of dicts with player_id, player_name, max_elo, date_reached,
            inactive, disabled.
        """
        players = {p.id: p for p in self.db.query(Player).all()}

        # Load ALL matches in one query, sorted chronologically
        all_matches = (
            self.db.query(Match)
            .order_by(Match.date.asc(), Match.created_at.asc(), Match.id.asc())
            .all()
        )

        # Compute ATH Elo per player in memory
        player_ath: dict[int, dict] = {}  # pid -> {"max_elo": float, "date": str}
        players_with_games: set[int] = set()

        for m in all_matches:
            players_with_games.add(m.player_a_id)
            players_with_games.add(m.player_b_id)

            # Player A
            pid_a = m.player_a_id
            elo_a = m.elo_after_a
            if pid_a not in player_ath or elo_a > player_ath[pid_a]["max_elo"]:
                player_ath[pid_a] = {"max_elo": elo_a, "date": m.date.isoformat()}

            # Player B
            pid_b = m.player_b_id
            elo_b = m.elo_after_b
            if pid_b not in player_ath or elo_b > player_ath[pid_b]["max_elo"]:
                player_ath[pid_b] = {"max_elo": elo_b, "date": m.date.isoformat()}

        # Fallback for players with start_elo but no ATH from matches
        for pid, p in players.items():
            if pid not in player_ath:
                player_ath[pid] = {"max_elo": float(p.start_elo), "date": None}

        today = date.today()

        result = []
        for pid, p in players.items():
            is_inactive = RankingService._is_inactive(p, today)

            # Disabled and inactive players are only shown when the
            # "include inactive / disabled" flag is set.
            if not include_inactive and (p.disabled or is_inactive):
                continue

            ath = player_ath.get(pid, {"max_elo": float(p.start_elo), "date": None})
            result.append(
                {
                    "player_id": pid,
                    "player_name": p.name,
                    "max_elo": ath["max_elo"],
                    "date_reached": ath["date"],
                    "inactive": is_inactive,
                    "disabled": p.disabled,
                }
            )

        # Sort by max_elo descending
        result.sort(key=lambda x: (-x["max_elo"], x["player_name"]))
        return result

    def get_all_time_high_ranking(self, player_id: int) -> dict:
        """Get the best ranking position ever achieved by a player.

        "Best" means the LOWEST rank number ever reached (best = #1). The
        implementation tracks the minimum rank seen on each date the player
        played; MAX is never used (Fix #4).

        The denominator for each date is the full roster that existed on
        that date: every member entered by then (entry_date, Fix #3 II) -
        whether or not they had played yet, regardless of inactivity, and
        including players who are currently disabled. Disabled players stay
        in place (they are merely forbidden to play new matches), so
        disabling top players can never inflate anyone's Best Rank - live or
        historically.

        Args:
            player_id: The player's ID.

        Returns:
            Dict with best_rank and date_reached.

        Performance note (Fix L10): this loads every match and re-sorts the
        player rankings on each target date, so it is O(matches * players) per
        call. That is fine for club-scale histories (a few thousand matches);
        if a much larger dataset ever shows up, precompute the all-time
        per-player best rank in a background job instead of per request.
        """
        # Load the entire roster (disabled players included): disabled players are
        # a permanent part of the historical field, so the full history is
        # needed to rank the target against.
        all_players = self.db.query(Player).all()
        if not all_players:
            return {"best_rank": None, "date_reached": None}

        player_map = {p.id: p for p in all_players}
        if player_id not in player_map:
            return {"best_rank": None, "date_reached": None}

        # Load all matches sorted chronologically
        all_matches = (
            self.db.query(Match)
            .order_by(Match.date.asc(), Match.created_at.asc(), Match.id.asc())
            .all()
        )

        if not all_matches:
            return {"best_rank": None, "date_reached": None}

        # Build Elo snapshots: at each match, track each player's running Elo
        # Initialize all players to their start_elo
        current_elos: dict[int, float] = {p.id: float(p.start_elo) for p in all_players}

        # Fix #3 II: a player is a competitor from their explicit entry date
        # onwards (fallback: creation date for legacy NULLs). Date-only by
        # design - the time-of-day of created_at or entry_date never counts;
        # a player who joined at 23:59 exists just as much as one at 00:01 on
        # the same calendar day. Matches are processed in date order, so
        # players become eligible monotonically: sort by entry date and
        # advance a pointer as the walking date passes it.
        def _entry_date(player: Player) -> date:
            if player.entry_date is not None:
                return player.entry_date
            return player.created_at.date()

        players_by_entry = sorted(all_players, key=_entry_date)
        next_entry = 0
        eligible_ids: set[int] = set()

        # Collect unique dates where the target player played
        target_match_dates: list[date] = []
        for m in all_matches:
            if m.player_a_id == player_id or m.player_b_id == player_id:
                target_match_dates.append(m.date)

        if not target_match_dates:
            return {"best_rank": None, "date_reached": None}

        target_date_set = set(target_match_dates)
        best_rank = None
        best_date = None

        # Walk through all the matches, updating Elo, and check ranking at
        # every date the target player played
        for m in all_matches:
            # Players whose effective entry date has been reached become
            # rankable now.
            while (
                next_entry < len(players_by_entry)
                and _entry_date(players_by_entry[next_entry]) <= m.date
            ):
                eligible_ids.add(players_by_entry[next_entry].id)
                next_entry += 1

            # Update elos for this match
            if m.player_a_id in current_elos:
                current_elos[m.player_a_id] = m.elo_after_a
            if m.player_b_id in current_elos:
                current_elos[m.player_b_id] = m.elo_after_b

            # Only compute ranking at dates the target player played
            if m.date in target_date_set and player_id in eligible_ids:
                # Rank every player who had entered by this date by their
                # current Elo - disabled players stay in the field.
                rankings = sorted(
                    ((pid, elo) for pid, elo in current_elos.items() if pid in eligible_ids),
                    key=lambda x: (-x[1], x[0]),
                )
                for rank, (pid, _) in enumerate(rankings, 1):
                    if pid == player_id:
                        if best_rank is None or rank < best_rank:
                            best_rank = rank
                            best_date = m.date.isoformat()
                        break

        return {"best_rank": best_rank, "date_reached": best_date}
