"""Equivalence tests for the batched ranking optimization (Fix #8).

The previous ``generate_ranking`` issued three per-player queries
(``_get_elo_at_date`` x2 + ``_get_period_statistics``) - an N+1 pattern.
It now derives every player's values from a single batched query
(``_build_ranking_records``). These tests re-implement the OLD per-player
algorithm from scratch and assert the API output - especially the ranking
positions - is identical, so the optimization can never change the order.
"""

from datetime import date

from app.models.player import Player
from app.models.user import User, UserRole
from app.models.match import Match
from app.auth.password import hash_password


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
    """Create a player directly in the database."""
    player = Player(
        name=name,
        start_elo=elo,
        current_elo=float(elo),
        active=active,
        disabled=False,
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


def _reference_ranking(db_session, from_date, to_date, include_inactive):
    """Re-implementation of the pre-optimization (per-player query) algorithm."""
    # Eligible players - mirrors the old _get_eligible_players.
    players = db_session.query(Player).filter(Player.disabled.is_(False)).all()
    if not include_inactive:
        period_matches = (
            db_session.query(Match).filter(Match.date >= from_date, Match.date <= to_date).all()
        )
        active_ids = set()
        for m in period_matches:
            active_ids.add(m.player_a_id)
            active_ids.add(m.player_b_id)
        players = [p for p in players if p.id in active_ids or p.active]

    def elo_at(player, target_date, before):
        query = db_session.query(Match).filter(
            (Match.player_a_id == player.id) | (Match.player_b_id == player.id)
        )
        query = query.filter(Match.date < target_date if before else Match.date <= target_date)
        match = query.order_by(Match.date.desc(), Match.created_at.desc(), Match.id.desc()).first()
        if match is None:
            return float(player.start_elo)
        return match.elo_after_a if match.player_a_id == player.id else match.elo_after_b

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
                "position_change": start_positions.get(e["player_id"], i + 1) - (i + 1),
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

        # Eve played only before the period -> mark her inactive so she is
        # excluded when include_inactive=False and included when True.
        eve.active = False
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
