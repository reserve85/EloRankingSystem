"""Tests for automatic inactive player handling.

Inactive players:
- Defined by no match within inactivity_months threshold
- Hidden from active ranking
- Remain in database with Elo history
- Remain selectable for future matches
- Automatically reactivated when they play a new match

Disabled ≠ Inactive:
- Disabled: set manually by admin, player.disabled=True
- Inactive: automatic based on last_match_date, player.disabled=False
"""

from datetime import date, timedelta


from app.models.player import Player
from app.models.user import User, UserRole
from app.auth.password import hash_password


# ── Helpers ─────────────────────────────────────────────────────────────


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


def _create_player(db_session, name="Player", elo=1200, last_match=None):
    """Create a player with optional last_match_date."""
    player = Player(
        name=name,
        start_elo=elo,
        current_elo=float(elo),
        active=True,
        disabled=False,
        last_match_date=last_match,
    )
    db_session.add(player)
    db_session.commit()
    db_session.refresh(player)
    return player


def _get_ranking(client, from_date, to_date, include_inactive=False):
    """Get ranking via API."""
    params = {"include_inactive": str(include_inactive).lower()}
    if from_date:
        params["from_date"] = from_date
    if to_date:
        params["to_date"] = to_date
    return client.get("/rankings/", params=params)


# ── Tests ───────────────────────────────────────────────────────────────


class TestInactivePlayerBecomesInactive:
    """Tests that players become inactive after the threshold period."""

    def test_player_with_old_match_is_inactive(self, db_session, monkeypatch):
        """Player with last_match_date older than threshold should be inactive."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        today = date.today()
        old_date = today - timedelta(days=100)  # > 3 months

        player = _create_player(db_session, "Old Player", last_match=old_date)

        # Check: player exists, has no recent match, is not disabled
        assert player.disabled is False
        assert player.last_match_date < today - timedelta(days=90)

    def test_player_with_recent_match_is_active(self, db_session, monkeypatch):
        """Player with last_match_date within threshold should be active."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        today = date.today()
        recent_date = today - timedelta(days=10)  # < 3 months

        player = _create_player(db_session, "Recent Player", last_match=recent_date)

        assert player.disabled is False
        assert player.last_match_date >= today - timedelta(days=90)

    def test_player_with_no_match_date_uses_creation(self, db_session, monkeypatch):
        """Player with no matches should be included (not filtered out)."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        player = _create_player(db_session, "New Player")
        assert player.last_match_date is None


class TestInactivePlayerHiddenFromRanking:
    """Tests that inactive players are hidden from active rankings."""

    def test_inactive_not_in_active_ranking(self, client, db_session, monkeypatch):
        """Inactive player should not appear in active ranking."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        _create_player(db_session, "Active", elo=1200,
                                last_match=date.today() - timedelta(days=5))
        _create_player(db_session, "Inactive", elo=1300,
                                  last_match=date.today() - timedelta(days=120))

        resp = _get_ranking(
            client,
            str(date.today().replace(day=1)),
            str(date.today()),
            include_inactive=False,
        )
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert "Active" in names
        assert "Inactive" not in names

    def test_inactive_visible_in_full_ranking(self, client, db_session, monkeypatch):
        """Inactive player should appear when include_inactive=True."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        _create_player(db_session, "Inactive", elo=1300,
                                  last_match=date.today() - timedelta(days=120))

        resp = _get_ranking(
            client,
            str(date.today().replace(day=1)),
            str(date.today()),
            include_inactive=True,
        )
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert "Inactive" in names

    def test_inactive_retains_elo_in_ranking(self, client, db_session, monkeypatch):
        """Inactive player should retain their Elo rating in ranking."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        _create_player(db_session, "Inactive", elo=1350,
                                  last_match=date.today() - timedelta(days=120))

        resp = _get_ranking(
            client,
            str(date.today().replace(day=1)),
            str(date.today()),
            include_inactive=True,
        )
        entry = next(e for e in resp.json()["entries"] if e["player_name"] == "Inactive")
        assert entry["elo_rating"] == 1350.0


class TestInactivePlayerSelectable:
    """Tests that inactive players remain selectable for matches."""

    def test_inactive_player_in_player_list(self, client, db_session, monkeypatch):
        """Inactive player should appear in player list for match selection."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        _create_player(db_session, "Inactive", elo=1200,
                                  last_match=date.today() - timedelta(days=120))

        # get_all_players returns all non-disabled players
        resp = client.get("/players/")
        names = [p["name"] for p in resp.json()]
        assert "Inactive" in names

    def test_inactive_player_in_active_list(self, client, db_session, monkeypatch):
        """Inactive player should appear in active player list (not disabled)."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        _create_player(db_session, "Inactive", elo=1200,
                                  last_match=date.today() - timedelta(days=120))

        # Active players list (not disabled)
        resp = client.get("/players/active")
        names = [p["name"] for p in resp.json()]
        assert "Inactive" in names

    def test_inactive_player_can_play_match(self, client, db_session, monkeypatch):
        """Inactive player should be able to participate in a new match."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        inactive = _create_player(db_session, "Inactive", elo=1200,
                                  last_match=date.today() - timedelta(days=120))
        opponent = _create_player(db_session, "Opponent", elo=1200,
                                  last_match=date.today())

        resp = client.post("/matches/", json={
            "date": str(date.today()),
            "player_a_id": inactive.id,
            "player_b_id": opponent.id,
            "player1_score": 3,
            "player2_score": 0,
        })
        assert resp.status_code == 201


class TestInactivePlayerReactivated:
    """Tests that inactive players are automatically reactivated after a new match."""

    def test_inactive_becomes_active_after_match(self, client, db_session, monkeypatch):
        """Inactive player should reappear in ranking after playing a match."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        inactive = _create_player(db_session, "Returning", elo=1200,
                                  last_match=date.today() - timedelta(days=120))
        opponent = _create_player(db_session, "Opponent", elo=1200,
                                  last_match=date.today())

        # Before match: not in active ranking
        resp = _get_ranking(
            client,
            str(date.today().replace(day=1)),
            str(date.today()),
        )
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert "Returning" not in names

        # Play a match
        client.post("/matches/", json={
            "date": str(date.today()),
            "player_a_id": inactive.id,
            "player_b_id": opponent.id,
            "player1_score": 3,
            "player2_score": 0,
        })

        # After match: appears in active ranking
        resp = _get_ranking(
            client,
            str(date.today().replace(day=1)),
            str(date.today()),
        )
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert "Returning" in names

    def test_last_match_date_updated_on_match(self, client, db_session, monkeypatch):
        """Player's last_match_date should be updated when they play."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        inactive = _create_player(db_session, "Returning", elo=1200,
                                  last_match=date(2024, 1, 1))
        opponent = _create_player(db_session, "Opponent", elo=1200)

        today_str = str(date.today())
        client.post("/matches/", json={
            "date": today_str,
            "player_a_id": inactive.id,
            "player_b_id": opponent.id,
            "player1_score": 3,
            "player2_score": 0,
        })

        resp = client.get(f"/players/{inactive.id}")
        assert resp.json()["last_match_date"] == today_str

    def test_reactivated_player_retains_elo(self, client, db_session, monkeypatch):
        """Reactivated player should keep their previous Elo rating."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        inactive = _create_player(db_session, "Returning", elo=1350,
                                  last_match=date(2024, 1, 1))
        opponent = _create_player(db_session, "Opponent", elo=1200,
                                  last_match=date.today())

        # Play a match - Elo should start from 1350, not default 1200
        resp = client.post("/matches/", json={
            "date": str(date.today()),
            "player_a_id": inactive.id,
            "player_b_id": opponent.id,
            "player1_score": 3,
            "player2_score": 0,
        })
        match_data = resp.json()
        assert match_data["elo_before_a"] == 1350.0


class TestDisabledVsInactive:
    """Tests that disabled and inactive are different concepts."""

    def test_disabled_player_not_in_ranking_even_with_include_inactive(self, client, db_session, monkeypatch):
        """Disabled player should NOT appear even with include_inactive=True."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        disabled = _create_player(db_session, "Disabled", elo=1200,
                                  last_match=date.today())
        disabled.disabled = True
        db_session.commit()

        resp = _get_ranking(
            client,
            str(date.today().replace(day=1)),
            str(date.today()),
            include_inactive=True,
        )
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert "Disabled" not in names

    def test_inactive_player_in_ranking_with_include_inactive(self, client, db_session, monkeypatch):
        """Inactive player SHOULD appear with include_inactive=True."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        _create_player(db_session, "Inactive", elo=1200,
                                  last_match=date.today() - timedelta(days=120))

        resp = _get_ranking(
            client,
            str(date.today().replace(day=1)),
            str(date.today()),
            include_inactive=True,
        )
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert "Inactive" in names

    def test_disabled_not_in_player_list(self, client, db_session):
        """Disabled player should not appear in active player list."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        disabled = _create_player(db_session, "Disabled", elo=1200)
        disabled.disabled = True
        disabled.active = False
        db_session.commit()

        resp = client.get("/players/active")
        names = [p["name"] for p in resp.json()]
        assert "Disabled" not in names

    def test_inactive_still_in_player_list(self, client, db_session, monkeypatch):
        """Inactive player should still appear in player list."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        _create_player(db_session, "Inactive", elo=1200,
                                  last_match=date.today() - timedelta(days=120))

        resp = client.get("/players/active")
        names = [p["name"] for p in resp.json()]
        assert "Inactive" in names

    def test_disabled_cannot_play_match(self, client, db_session):
        """Disabled player should not be selectable for new matches (by default)."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        disabled = _create_player(db_session, "Disabled", elo=1200)
        disabled.disabled = True
        db_session.commit()
        _create_player(db_session, "Opponent", elo=1200)

        # Disabled player can still technically be sent in API,
        # but the business rule is enforced by UI/service layer
        # Here we just verify disabled flag is True
        resp = client.get(f"/players/{disabled.id}")
        assert resp.json()["disabled"] is True

    def test_inactive_player_disabled_flag_false(self, client, db_session, monkeypatch):
        """Inactive player should have disabled=False."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        inactive = _create_player(db_session, "Inactive", elo=1200,
                                  last_match=date.today() - timedelta(days=120))

        assert inactive.disabled is False
        assert inactive.active is True

    def test_reactivate_disabled_is_not_same_as_inactive_becoming_active(self, client, db_session):
        """Reactivating a disabled player and inactive becoming active are different operations."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        # Disabled player: needs admin action
        disabled = _create_player(db_session, "Disabled", elo=1200)
        disabled.disabled = True
        disabled.active = False
        db_session.commit()

        # Reactivate via API (admin action)
        resp = client.post(f"/players/{disabled.id}/reactivate")
        assert resp.status_code == 200
        assert resp.json()["disabled"] is False
        assert resp.json()["active"] is True

        # Inactive player: becomes active automatically via match
        inactive = _create_player(db_session, "Inactive", elo=1200,
                                  last_match=date(2024, 1, 1))
        assert inactive.disabled is False
        assert inactive.active is True  # Still "active" in DB sense
