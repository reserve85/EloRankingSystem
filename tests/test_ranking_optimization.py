"""Equivalence tests for the batched ranking optimization (Fix #8).

The previous ``generate_ranking`` issued three per-player queries
(``_get_elo_at_date`` x2 + ``_get_period_statistics``) - an N+1 pattern.
It now derives every player's values from a single batched query
(``_build_ranking_records``). These tests re-implement the OLD per-player
algorithm from scratch and assert the API output - especially the ranking
positions - is identical, so the optimization can never change the order.
"""

import time
from contextlib import contextmanager

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import event, insert

from app.models.player import Player
from app.models.user import User, UserRole
from app.models.match import Match
from app.auth.password import hash_password
from app.services.ranking import RankingService


def _login_as(client, db_session, username, password, role):
    """Create a user and log in."""
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    client.post("/auth/login", data={"username": username, "password": password})
    return user


def _create_player(db_session, name, elo=1200, active=True):
    """Create a player directly in the database (entered before 2025)."""
    player = Player(
        name=name,
        start_elo=elo,
        current_elo=float(elo),
        active=active,
        disabled=False,
        created_at=datetime(2024, 12, 1, 12, 0, 0),
        entry_date=date(2024, 12, 1),
    )
    db_session.add(player)
    db_session.commit()
    db_session.refresh(player)
    return player


def _create_match(client, pa_id, pb_id, winner_id, match_date, **stats):
    """Create a match via the API (real Elo snapshots are computed)."""
    score_a = 3 if winner_id == pa_id else 0
    score_b = 3 if winner_id == pb_id else 0
    payload = {
        "date": match_date,
        "player_a_id": pa_id,
        "player_b_id": pb_id,
        "player1_score": score_a,
        "player2_score": score_b,
    }
    payload.update(stats)
    resp = client.post("/matches/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _inactive_cutoff(as_of_date):
    """Cutoff date for inactivity - mirrors ``RankingService._inactive_cutoff``."""
    import calendar

    months = 3  # default settings.inactivity_months (tests use the default)
    year = as_of_date.year
    month = as_of_date.month - months
    while month <= 0:
        month += 12
        year -= 1
    day = min(as_of_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _reference_ranking(db_session, from_date, to_date, include_inactive):
    """Re-implementation of the pre-optimization (per-player query) algorithm."""

    # Eligible players - mirrors ``_get_eligible_players``. Fix #3 II: a
    # player is a competitor from their explicit entry date onwards
    # (fallback: created_at date for legacy rows with a NULL entry_date).
    def _entry(player):
        if player.entry_date is not None:
            return player.entry_date
        return player.created_at.date()

    players = db_session.query(Player).all()
    players = [p for p in players if _entry(p) <= to_date]
    if not include_inactive:
        period_matches = (
            db_session.query(Match).filter(Match.date >= from_date, Match.date <= to_date).all()
        )
        active_ids = set()
        for m in period_matches:
            active_ids.add(m.player_a_id)
            active_ids.add(m.player_b_id)
        cutoff = _inactive_cutoff(to_date)
        players = [
            p
            for p in players
            if p.id in active_ids or (p.last_match_date is not None and p.last_match_date >= cutoff)
        ]
        # Disabled players are hidden without the "include inactive / disabled" flag.
        players = [p for p in players if not p.disabled]

    def elo_at(player, target_date, before):
        query = db_session.query(Match).filter(
            (Match.player_a_id == player.id) | (Match.player_b_id == player.id)
        )
        query = query.filter(Match.date < target_date if before else Match.date <= target_date)
        match = query.order_by(Match.date.desc(), Match.created_at.desc(), Match.id.desc()).first()
        if match is None:
            return float(player.start_elo)
        return match.elo_after_a if match.player_a_id == player.id else match.elo_after_b

    def has_any_match(player, target_date):
        """Whether the player has any match up to ``target_date`` (Fix #1)."""
        query = db_session.query(Match).filter(
            (Match.player_a_id == player.id) | (Match.player_b_id == player.id)
        )
        return query.filter(Match.date <= target_date).first() is not None

    def period_stats(pid):
        matches = (
            db_session.query(Match)
            .filter(
                ((Match.player_a_id == pid) | (Match.player_b_id == pid))
                & (Match.date >= from_date)
                & (Match.date <= to_date)
            )
            .all()
        )
        total_180s = 0
        high_finishes = []
        low_darts = []
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
            "match_count": len(matches),
            "total_180s": total_180s,
            "high_finishes": sorted(high_finishes, reverse=True),
            "low_darts": sorted(low_darts),
        }

    entries = []
    for player in players:
        s = period_stats(player.id)
        start = elo_at(player, from_date, before=True)
        end = elo_at(player, to_date, before=False)
        entries.append(
            {
                "player_id": player.id,
                "player_name": player.name,
                "elo_rating": end,
                "elo_change": end - start,
                "start_elo": start,
                "has_match_history": has_any_match(player, to_date),
                "total_matches": s["match_count"],
                "total_180s": s["total_180s"],
                "high_finishes": s["high_finishes"],
                "low_darts": s["low_darts"],
            }
        )

    entries.sort(key=lambda e: (-e["elo_rating"], e["player_name"]))
    start_entries = sorted(entries, key=lambda e: (-e["start_elo"], e["player_name"]))
    start_positions = {e["player_id"]: i + 1 for i, e in enumerate(start_entries)}

    result = []
    for i, e in enumerate(entries):
        result.append(
            {
                "player_id": e["player_id"],
                "position": i + 1,
                # Fix #1: no match history up to to_date -> no previous ranking
                # position -> the API reports None (rendered as '-').
                "position_change": (
                    start_positions.get(e["player_id"], i + 1) - (i + 1)
                    if e["has_match_history"]
                    else None
                ),
                "elo_rating": round(e["elo_rating"], 6),
                "elo_change": round(e["elo_change"], 6),
                "total_matches": e["total_matches"],
                "total_180s": e["total_180s"],
                "high_finishes": e["high_finishes"],
                "low_darts": e["low_darts"],
            }
        )
    return result


def _api_entries(client, from_date, to_date, include_inactive):
    """Get the API ranking as a comparable list of dicts."""
    resp = client.get(
        "/rankings/",
        params={
            "include_inactive": str(include_inactive).lower(),
            "from_date": from_date,
            "to_date": to_date,
        },
    )
    assert resp.status_code == 200
    out = []
    for e in resp.json()["entries"]:
        out.append(
            {
                "player_id": e["player_id"],
                "position": e["position"],
                "position_change": e["position_change"],
                "elo_rating": round(e["elo_rating"], 6),
                "elo_change": round(e["elo_change"], 6),
                "total_matches": e["total_matches"],
                "total_180s": e["total_180s"],
                "high_finishes": e["high_finishes"],
                "low_darts": e["low_darts"],
            }
        )
    return out


class TestBatchedRankingEquivalence:
    """The batched ranking must produce identical values and positions."""

    def _seed(self, client, db_session):
        """Players + matches before, inside, and after the ranking period."""
        alice = _create_player(db_session, "Alice", elo=1200)
        bob = _create_player(db_session, "Bob", elo=1200)
        carol = _create_player(db_session, "Carol", elo=1400)  # no matches at all
        dan = _create_player(db_session, "Dan", elo=1100)
        eve = _create_player(db_session, "Eve", elo=1300)

        # Before the period
        _create_match(client, alice.id, dan.id, alice.id, "2025-05-15")
        _create_match(client, eve.id, dan.id, eve.id, "2025-05-20")

        # Inside the period (dart stats included)
        _create_match(
            client,
            alice.id,
            bob.id,
            alice.id,
            "2025-06-05",
            player_a_180s=2,
            player_a_high_finishes=[120],
            player_b_low_darts=[15],
        )
        # Two matches on the SAME day exercise the created_at/id tie-break.
        _create_match(
            client, alice.id, bob.id, bob.id, "2025-06-06", player1_score=2, player2_score=3
        )
        _create_match(client, dan.id, alice.id, dan.id, "2025-06-20")

        # After the period
        _create_match(client, bob.id, alice.id, alice.id, "2025-07-10")

        # Eve played only before the period -> push her last match before the
        # inactivity cutoff so she is excluded when include_inactive=False
        # and included when True.
        eve.last_match_date = date(2025, 1, 1)
        db_session.commit()
        return alice, bob, carol, dan, eve

    def test_ranking_equals_reference_algorithm(self, client, db_session):
        """API output is identical to the old per-player algorithm everywhere."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        self._seed(client, db_session)

        windows = [
            (date(2025, 6, 1), date(2025, 6, 30)),  # the classic month window
            (date(2025, 1, 1), date(2025, 12, 31)),  # full history
            (date(2025, 6, 1), date(2025, 6, 1)),  # single-day window
        ]
        for include_inactive in (False, True):
            for from_date, to_date in windows:
                api = _api_entries(
                    client, from_date.isoformat(), to_date.isoformat(), include_inactive
                )
                reference = _reference_ranking(db_session, from_date, to_date, include_inactive)
                assert api == reference, (
                    f"mismatch (include_inactive={include_inactive}, "
                    f"{from_date}..{to_date})\napi: {api}\nref: {reference}"
                )

    def test_positions_are_stable_across_runs(self, client, db_session):
        """Positions specifically cannot drift between runs of the batch path."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        self._seed(client, db_session)

        first = _api_entries(client, "2025-06-01", "2025-06-30", False)
        second = _api_entries(client, "2025-06-01", "2025-06-30", False)

        assert first == second
        assert [e["position"] for e in first] == sorted(e["position"] for e in first)


class TestBulkScaleGuard:
    """Tripwire for the ranking replay cost (review finding #11, Tier 0).

    ``generate_ranking`` and ``get_all_time_high_ranking`` re-scan the match
    table on every request. That is fine at club scale but has an undocumented
    ceiling; a regression (e.g. a reintroduced N+1 or an accidental O(N^2)
    replay) should fail CI instead of silently degrading. These tests seed a
    club-scale history (``N_PLAYERS`` players / ``N_MATCHES`` matches) directly
    via bulk inserts and assert two things per call:

    1. a generous wall-clock budget - a gross algorithmic regression blows
       past it;
    2. a deterministic SELECT-count ceiling - catches the N+1 shape that
       wall-clock only trips flakily.

    Marked ``slow`` so ``-m 'not slow'`` deselects it locally; CI (pytest
    tests/) runs the full suite including these.
    """

    # Club-scale history: 150 players, ~10k matches across ~2 years.
    N_PLAYERS = 150
    N_MATCHES = 10_000
    WINDOW_DAYS = 730

    # Generous budgets: local runs of these calls take ~0.1-1.5s. The 10x+
    # headroom keeps this a tripwire instead of a flake on slow CI runners.
    GENERATE_RANKING_BUDGET_S = 20.0
    ATH_RANKING_BUDGET_S = 30.0

    # Reviewed SELECT shapes: generate_ranking ~= 2-3 statements (players +
    # active-ids subquery + 1 match scan), all_time_high_ranking == 2 (players
    # + 1 match scan). The ceilings are defensive; a per-player N+1 would
    # issue 300+ statements.
    GENERATE_RANKING_MAX_SELECTS = 12
    ATH_RANKING_MAX_SELECTS = 8

    def _player_rows(self) -> list[dict]:
        """All players entered before the seeded match window."""
        today = date.today()
        return [
            {
                "id": pid,
                "name": f"Player {pid:03d}",
                "start_elo": 1200,
                "current_elo": float(1200 + (pid * 7) % 400),
                "entry_date": today - timedelta(days=800 - (pid % 700)),
                "active": True,
                "disabled": pid == self.N_PLAYERS,
                "last_match_date": None,
            }
            for pid in range(1, self.N_PLAYERS + 1)
        ]

    def _schedule(self) -> list[tuple[int, int, int, bool]]:
        """Deterministic (days_ago, player_a, player_b, pa_wins) schedule.

        - Every player plays once in the final 30 days, so all of them are
          in-period active players for ``include_inactive=False``.
        - Player 1 (the ATH target) plays once per day across the whole
          window, giving ``get_all_time_high_ranking`` ~730 distinct dates to
          re-rank.
        - The rest is rotating pairs across the window.
        """
        schedule: list[tuple[int, int, int, bool]] = []
        for i in range(self.N_PLAYERS):
            a = i + 1
            b = (i + 1) % self.N_PLAYERS + 1
            schedule.append((i % 30, a, b, i % 2 == 0))
        for day in range(self.WINDOW_DAYS):
            schedule.append((day, 1, 2 + day % (self.N_PLAYERS - 1), day % 2 == 0))
        remaining = self.N_MATCHES - len(schedule)
        for idx in range(remaining):
            a = idx % self.N_PLAYERS + 1
            b = (idx * 37 + 3) % self.N_PLAYERS + 1
            if b == a:
                b = a % self.N_PLAYERS + 1
            schedule.append((idx % self.WINDOW_DAYS, a, b, idx % 3 != 0))
        return schedule

    def _seed_bulk(self, db_session) -> None:
        """Insert players + matches with Core bulk inserts (fast, no ORM)."""
        match_rows: list[dict] = []
        today = date.today()
        for match_id, (days_ago, a, b, pa_wins) in enumerate(self._schedule(), start=1):
            d = today - timedelta(days=days_ago)
            base = 1000.0 + (match_id % 400)
            before_b = base + 40.0 + (match_id // 3) % 120
            change_a = 8.0 if pa_wins else -8.0
            match_rows.append(
                {
                    "id": match_id,
                    "date": d,
                    "player_a_id": a,
                    "player_b_id": b,
                    "best_of_legs": 5,
                    "player1_score": 3 if pa_wins else 0,
                    "player2_score": 0 if pa_wins else 3,
                    "winner_id": a if pa_wins else b,
                    "loser_id": b if pa_wins else a,
                    "elo_before_a": base,
                    "elo_before_b": before_b,
                    "elo_after_a": base + change_a,
                    "elo_after_b": before_b - change_a,
                    "elo_change_a": change_a,
                    "elo_change_b": -change_a,
                    "k_factor": 32.0,
                    "player_a_180s": match_id % 3,
                    "player_b_180s": match_id % 2,
                }
            )
        db_session.execute(insert(Player), self._player_rows())
        db_session.execute(insert(Match), match_rows)
        db_session.commit()

    @contextmanager
    def _count_selects(self, db_session):
        """Count SELECT statements executed against the test engine."""

        engine = db_session.get_bind()
        counter = {"selects": 0}

        def _before_execute(conn, clauseelement, multiparams, params, execution_options):
            if str(clauseelement).lstrip().upper().startswith("SELECT"):
                counter["selects"] += 1

        event.listen(engine, "before_execute", _before_execute)
        try:
            yield counter
        finally:
            event.remove(engine, "before_execute", _before_execute)

    @pytest.mark.slow
    def test_generate_ranking_scale_and_query_budget(self, db_session):
        """The monthly ranking path stays bounded at club-scale data."""
        self._seed_bulk(db_session)
        service = RankingService(db_session)
        to_date = date.today()
        from_date = to_date - timedelta(days=365)

        t0 = time.perf_counter()
        with self._count_selects(db_session) as counter:
            ranking = service.generate_ranking(from_date=from_date, to_date=to_date)
        elapsed = time.perf_counter() - t0

        # Every non-disabled player played in the last 30 days -> all 149 are
        # in the field (the disabled one is hidden without the flag).
        assert len(ranking.entries) == self.N_PLAYERS - 1
        assert elapsed < self.GENERATE_RANKING_BUDGET_S, (
            f"generate_ranking over {self.N_MATCHES} matches took {elapsed:.2f}s "
            f"(budget {self.GENERATE_RANKING_BUDGET_S}s)"
        )
        assert counter["selects"] <= self.GENERATE_RANKING_MAX_SELECTS, (
            f"generate_ranking issued {counter['selects']} SELECTs "
            f"(ceiling {self.GENERATE_RANKING_MAX_SELECTS}); N+1 regression?"
        )

    @pytest.mark.slow
    def test_all_time_high_ranking_scale_and_query_budget(self, db_session):
        """The all-time-high ranking path stays bounded at club-scale data."""
        self._seed_bulk(db_session)
        service = RankingService(db_session)

        t0 = time.perf_counter()
        with self._count_selects(db_session) as counter:
            result = service.get_all_time_high_ranking(1)
        elapsed = time.perf_counter() - t0

        assert result["best_rank"] is not None
        assert elapsed < self.ATH_RANKING_BUDGET_S, (
            f"get_all_time_high_ranking over {self.N_MATCHES} matches took "
            f"{elapsed:.2f}s (budget {self.ATH_RANKING_BUDGET_S}s)"
        )
        assert counter["selects"] <= self.ATH_RANKING_MAX_SELECTS, (
            f"get_all_time_high_ranking issued {counter['selects']} SELECTs "
            f"(ceiling {self.ATH_RANKING_MAX_SELECTS}); N+1 regression?"
        )
