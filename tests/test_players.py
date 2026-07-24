"""Tests for player management - service, repository, routes, and permissions."""

import pytest

from app.models.player import Player
from app.models.user import User, UserRole
from app.auth.password import hash_password
from app.schemas.player import PlayerCreate, PlayerUpdate


# ── Helper ──────────────────────────────────────────────────────────────


def _login_as(client, db_session, username, password, role):
    """Create a user and log in, returning the client with cookie set."""
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


def _create_player_db(db_session, name="Test Player", start_elo=1200):
    """Helper to create a player directly in the database."""
    player = Player(
        name=name,
        start_elo=start_elo,
        current_elo=float(start_elo),
        active=True,
        disabled=False,
    )
    db_session.add(player)
    db_session.commit()
    db_session.refresh(player)
    return player


# ── Service Tests ───────────────────────────────────────────────────────


class TestPlayerServiceCreate:
    """Tests for player creation via service."""

    def test_create_player_with_default_elo(self, db_session, monkeypatch):
        """Creating player without start_elo should use config default."""
        monkeypatch.setattr("app.services.player.settings.default_elo", 1200)
        from app.services.player import PlayerService

        service = PlayerService(db_session)
        player = service.create_player(PlayerCreate(name="New Player"))

        assert player.id is not None
        assert player.name == "New Player"
        assert player.start_elo == 1200
        assert player.current_elo == 1200.0
        assert player.active is False
        assert player.disabled is False

    def test_create_player_with_custom_elo(self, db_session, monkeypatch):
        """Creating player with explicit start_elo should use it."""
        monkeypatch.setattr("app.services.player.settings.default_elo", 1200)
        from app.services.player import PlayerService

        service = PlayerService(db_session)
        player = service.create_player(PlayerCreate(name="Pro Player", start_elo=1500))

        assert player.start_elo == 1500
        assert player.current_elo == 1500.0

    def test_create_player_duplicate_name_raises(self, db_session, monkeypatch):
        """Creating player with duplicate name should raise 409."""
        monkeypatch.setattr("app.services.player.settings.default_elo", 1200)
        from app.services.player import PlayerService

        service = PlayerService(db_session)
        service.create_player(PlayerCreate(name="Duplicate"))

        with pytest.raises(Exception):
            service.create_player(PlayerCreate(name="Duplicate"))


class TestPlayerServiceOperations:
    """Tests for player service operations."""

    def test_get_player(self, db_session):
        """get_player should return the player."""
        from app.services.player import PlayerService

        player = _create_player_db(db_session, "Found Player")
        service = PlayerService(db_session)
        result = service.get_player(player.id)

        assert result.name == "Found Player"

    def test_get_player_not_found(self, db_session):
        """get_player with invalid ID should raise 404."""
        from app.services.player import PlayerService

        service = PlayerService(db_session)
        with pytest.raises(Exception):
            service.get_player(99999)

    def test_get_all_players(self, db_session):
        """get_all_players should return non-disabled players by default."""
        from app.services.player import PlayerService

        _create_player_db(db_session, "Active Player")
        disabled = _create_player_db(db_session, "Disabled Player")
        disabled.disabled = True
        db_session.commit()

        service = PlayerService(db_session)
        players = service.get_all_players()
        names = [p.name for p in players]
        assert "Active Player" in names
        assert "Disabled Player" not in names

    def test_get_all_players_include_disabled(self, db_session):
        """get_all_players(include_disabled=True) should return all."""
        from app.services.player import PlayerService

        _create_player_db(db_session, "Active Player")
        disabled = _create_player_db(db_session, "Disabled Player")
        disabled.disabled = True
        db_session.commit()

        service = PlayerService(db_session)
        players = service.get_all_players(include_disabled=True)
        names = [p.name for p in players]
        assert "Active Player" in names
        assert "Disabled Player" in names

    def test_get_active_players(self, db_session):
        """get_active_players should return only active, non-disabled players."""
        from app.services.player import PlayerService

        _create_player_db(db_session, "Active Player")
        disabled = _create_player_db(db_session, "Disabled Player")
        disabled.disabled = True
        disabled.active = False
        db_session.commit()

        service = PlayerService(db_session)
        players = service.get_active_players()
        assert len(players) == 1
        assert players[0].name == "Active Player"

    def test_update_player_name(self, db_session):
        """update_player should change the name."""
        from app.services.player import PlayerService

        player = _create_player_db(db_session, "Old Name")
        service = PlayerService(db_session)
        updated = service.update_player(player.id, PlayerUpdate(name="New Name"))

        assert updated.name == "New Name"

    def test_update_player_start_elo(self, db_session):
        """update_player should change start_elo."""
        from app.services.player import PlayerService

        player = _create_player_db(db_session, start_elo=1200)
        service = PlayerService(db_session)
        updated = service.update_player(player.id, PlayerUpdate(start_elo=1400))

        assert updated.start_elo == 1400

    def test_update_player_duplicate_name_raises(self, db_session):
        """Updating to a name that already exists should raise 409."""
        from app.services.player import PlayerService

        _create_player_db(db_session, "Player One")
        player2 = _create_player_db(db_session, "Player Two")

        service = PlayerService(db_session)
        with pytest.raises(Exception):
            service.update_player(player2.id, PlayerUpdate(name="Player One"))

    def test_disable_player(self, db_session):
        """disable_player should set disabled=True and active=False."""
        from app.services.player import PlayerService

        player = _create_player_db(db_session)
        service = PlayerService(db_session)
        result = service.disable_player(player.id)

        assert result.disabled is True
        assert result.active is False

    def test_reactivate_player(self, db_session):
        """reactivate_player should set disabled=False and active=True."""
        from app.services.player import PlayerService

        player = _create_player_db(db_session)
        player.disabled = True
        player.active = False
        db_session.commit()

        service = PlayerService(db_session)
        result = service.reactivate_player(player.id)

        assert result.disabled is False
        assert result.active is True

    def test_disable_preserves_in_database(self, db_session):
        """Disabled player should remain in database."""
        from app.services.player import PlayerService

        player = _create_player_db(db_session, "Preserved Player")
        service = PlayerService(db_session)
        service.disable_player(player.id)

        found = db_session.query(Player).filter(Player.id == player.id).first()
        assert found is not None
        assert found.disabled is True


# ── Route Tests ─────────────────────────────────────────────────────────


class TestPlayerRoutesAsAdmin:
    """Tests for player API routes with ADMIN role."""

    def test_create_player(self, client, db_session):
        """ADMIN should be able to create a player."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        response = client.post("/players/", json={"name": "New Player"})
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Player"
        assert data["start_elo"] == 1200
        assert data["current_elo"] == 1200.0
        assert data["active"] is False
        assert data["disabled"] is False

    def test_create_player_custom_elo(self, client, db_session):
        """ADMIN should be able to create a player with custom Elo."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        response = client.post("/players/", json={"name": "Pro", "start_elo": 1500})
        assert response.status_code == 201
        data = response.json()
        assert data["start_elo"] == 1500
        assert data["current_elo"] == 1500.0

    def test_list_players(self, client, db_session):
        """ADMIN should be able to list players."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        _create_player_db(db_session, "Listed Player")

        response = client.get("/players/")
        assert response.status_code == 200
        data = response.json()
        assert any(p["name"] == "Listed Player" for p in data)

    def test_list_active_players(self, client, db_session):
        """ADMIN should be able to list active players."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        _create_player_db(db_session, "Active Player")

        response = client.get("/players/active")
        assert response.status_code == 200

    def test_get_player(self, client, db_session):
        """ADMIN should be able to get a specific player."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        player = _create_player_db(db_session, "Get Me")

        response = client.get(f"/players/{player.id}")
        assert response.status_code == 200
        assert response.json()["name"] == "Get Me"

    def test_update_player(self, client, db_session):
        """ADMIN should be able to update a player."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        player = _create_player_db(db_session, "Update Me")

        response = client.put(f"/players/{player.id}", json={"name": "Updated"})
        assert response.status_code == 200
        assert response.json()["name"] == "Updated"

    def test_disable_player(self, client, db_session):
        """ADMIN should be able to disable a player."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        player = _create_player_db(db_session, "Disable Me")

        response = client.post(f"/players/{player.id}/disable")
        assert response.status_code == 200
        data = response.json()
        assert data["disabled"] is True
        assert data["active"] is False

    def test_reactivate_player(self, client, db_session):
        """ADMIN should be able to reactivate a player."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        player = _create_player_db(db_session)
        player.disabled = True
        player.active = False
        db_session.commit()

        response = client.post(f"/players/{player.id}/reactivate")
        assert response.status_code == 200
        data = response.json()
        assert data["disabled"] is False
        assert data["active"] is True


class TestPlayerRoutesAsSystem:
    """Tests for player API routes with SYSTEM role."""

    def test_system_can_create_player(self, client, db_session):
        """SYSTEM should be able to create a player."""
        _login_as(client, db_session, "system", "pass", UserRole.SYSTEM)

        response = client.post("/players/", json={"name": "System Created"})
        assert response.status_code == 201

    def test_system_can_disable_player(self, client, db_session):
        """SYSTEM should be able to disable a player."""
        _login_as(client, db_session, "system", "pass", UserRole.SYSTEM)
        player = _create_player_db(db_session)

        response = client.post(f"/players/{player.id}/disable")
        assert response.status_code == 200
        assert response.json()["disabled"] is True


class TestPlayerRoutesAsUser:
    """Tests for player API routes with USER role (restricted)."""

    def test_user_cannot_create_player(self, client, db_session):
        """USER should NOT be able to create a player (403)."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)

        response = client.post("/players/", json={"name": "Blocked"})
        assert response.status_code == 403

    def test_user_cannot_update_player(self, client, db_session):
        """USER should NOT be able to update a player (403)."""
        _login_as(client, db_session, "user2", "pass", UserRole.USER)
        player = _create_player_db(db_session)

        response = client.put(f"/players/{player.id}", json={"name": "Blocked"})
        assert response.status_code == 403

    def test_user_cannot_disable_player(self, client, db_session):
        """USER should NOT be able to disable a player (403)."""
        _login_as(client, db_session, "user3", "pass", UserRole.USER)
        player = _create_player_db(db_session)

        response = client.post(f"/players/{player.id}/disable")
        assert response.status_code == 403

    def test_user_cannot_reactivate_player(self, client, db_session):
        """USER should NOT be able to reactivate a player (403)."""
        _login_as(client, db_session, "user4", "pass", UserRole.USER)
        player = _create_player_db(db_session)
        player.disabled = True
        db_session.commit()

        response = client.post(f"/players/{player.id}/reactivate")
        assert response.status_code == 403

    def test_user_can_list_players(self, client, db_session):
        """USER should be able to list players (read-only)."""
        _login_as(client, db_session, "user5", "pass", UserRole.USER)
        _create_player_db(db_session, "Visible Player")

        response = client.get("/players/")
        assert response.status_code == 200

    def test_user_can_get_player(self, client, db_session):
        """USER should be able to get a specific player (read-only)."""
        _login_as(client, db_session, "user6", "pass", UserRole.USER)
        player = _create_player_db(db_session, "Readable Player")

        response = client.get(f"/players/{player.id}")
        assert response.status_code == 200
        assert response.json()["name"] == "Readable Player"

    def test_user_can_list_active_players(self, client, db_session):
        """USER should be able to list active players (read-only)."""
        _login_as(client, db_session, "user7", "pass", UserRole.USER)

        response = client.get("/players/active")
        assert response.status_code == 200


class TestPlayerRoutesUnauthenticated:
    """Tests for player API routes without authentication."""

    def test_unauthenticated_cannot_create(self, client, db_session):
        """Unauthenticated request should be rejected (401)."""
        response = client.post("/players/", json={"name": "Blocked"})
        assert response.status_code == 401

    def test_unauthenticated_cannot_list(self, client, db_session):
        """Unauthenticated request should be rejected (401)."""
        response = client.get("/players/")
        assert response.status_code == 401

    def test_unauthenticated_cannot_update(self, client, db_session):
        """Unauthenticated request should be rejected (401)."""
        response = client.put("/players/1", json={"name": "Blocked"})
        assert response.status_code == 401

    def test_unauthenticated_cannot_disable(self, client, db_session):
        """Unauthenticated request should be rejected (401)."""
        response = client.post("/players/1/disable")
        assert response.status_code == 401


class TestPlayerDisabledState:
    """Tests verifying disabled player behavior."""

    def test_disabled_player_visible_in_list_with_flag(self, client, db_session):
        """Disabled player should appear when include_disabled=True."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        player = _create_player_db(db_session, "Gone Player")
        player.disabled = True
        player.active = False
        db_session.commit()

        # Without flag - should not appear
        response = client.get("/players/")
        names = [p["name"] for p in response.json()]
        assert "Gone Player" not in names

        # With flag - should appear
        response = client.get("/players/?include_disabled=true")
        names = [p["name"] for p in response.json()]
        assert "Gone Player" in names

    def test_disabled_player_gettable_by_id(self, client, db_session):
        """Disabled player should still be gettable by ID."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        player = _create_player_db(db_session, "Historical Player")
        player.disabled = True
        db_session.commit()

        response = client.get(f"/players/{player.id}")
        assert response.status_code == 200
        assert response.json()["name"] == "Historical Player"

    def test_disable_and_reactivate_cycle(self, client, db_session):
        """Player can be disabled and reactivated multiple times."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        player = _create_player_db(db_session, "Cyclic Player")

        # Disable
        response = client.post(f"/players/{player.id}/disable")
        assert response.json()["disabled"] is True
        assert response.json()["active"] is False

        # Reactivate
        response = client.post(f"/players/{player.id}/reactivate")
        assert response.json()["disabled"] is False
        assert response.json()["active"] is True

        # Disable again
        response = client.post(f"/players/{player.id}/disable")
        assert response.json()["disabled"] is True


class TestPlayerInactiveByDefault:
    """Tests for Task 11: new players are inactive by default."""

    def test_new_player_created_inactive_via_api(self, client, db_session):
        """Newly created player via API should be inactive by default."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        response = client.post("/players/", json={"name": "New Inactive Player"})
        assert response.status_code == 201
        data = response.json()
        assert data["active"] is False
        assert data["disabled"] is False

    def test_new_player_created_inactive_via_service(self, db_session, monkeypatch):
        """Newly created player via service should be inactive by default."""
        monkeypatch.setattr("app.services.player.settings.default_elo", 1200)
        from app.services.player import PlayerService

        service = PlayerService(db_session)
        player = service.create_player(PlayerCreate(name="Service New Player"))
        assert player.active is False
        assert player.disabled is False

    def test_inactive_player_selectable_for_match(self, client, db_session):
        """Inactive (but not disabled) player should appear in /players/active."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        # Create inactive player
        response = client.post("/players/", json={"name": "Selectable"})
        assert response.status_code == 201

        # Should appear in /players/active
        response = client.get("/players/active")
        assert response.status_code == 200
        names = [p["name"] for p in response.json()]
        assert "Selectable" in names

    def test_disabled_player_not_selectable_for_match(self, client, db_session):
        """Disabled player should NOT appear in /players/active."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        # Create then disable player
        response = client.post("/players/", json={"name": "Disabled Selectable"})
        player_id = response.json()["id"]
        client.post(f"/players/{player_id}/disable")

        # Should NOT appear in /players/active
        response = client.get("/players/active")
        names = [p["name"] for p in response.json()]
        assert "Disabled Selectable" not in names

    def test_first_match_activates_player(self, client, db_session, monkeypatch):
        """Playing first match should automatically activate the player."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 999)

        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        # Create two inactive players
        resp_a = client.post("/players/", json={"name": "Player A"})
        resp_b = client.post("/players/", json={"name": "Player B"})
        pa_id = resp_a.json()["id"]
        pb_id = resp_b.json()["id"]

        assert resp_a.json()["active"] is False
        assert resp_b.json()["active"] is False

        # Play a match
        from datetime import date
        match_resp = client.post("/matches/", json={
            "date": str(date.today()),
            "player_a_id": pa_id,
            "player_b_id": pb_id,
            "player1_score": 3,
            "player2_score": 0,
        })
        assert match_resp.status_code == 200 or match_resp.status_code == 201

        # Both players should now be active
        pa_data = client.get(f"/players/{pa_id}").json()
        pb_data = client.get(f"/players/{pb_id}").json()
        assert pa_data["active"] is True
        assert pb_data["active"] is True


class TestPlayerStartEloRecalculation:
    """Tests for Task 22: Elo recalculation when start_elo is changed."""

    def test_changing_start_elo_recalculates_match_elo(self, client, db_session):
        """Changing start_elo should trigger full Elo recalculation for all matches."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        # Create two players with start_elo 1200
        resp_a = client.post("/players/", json={"name": "Recalc A", "start_elo": 1200})
        resp_b = client.post("/players/", json={"name": "Recalc B", "start_elo": 1200})
        pa_id = resp_a.json()["id"]
        pb_id = resp_b.json()["id"]

        # Play a match - Player A wins
        match_resp = client.post("/matches/", json={
            "date": "2025-06-01",
            "player_a_id": pa_id,
            "player_b_id": pb_id,
            "player1_score": 3,
            "player2_score": 0,
        })
        assert match_resp.status_code in (200, 201)

        # Get Elo values after first calculation
        match_data = match_resp.json()
        original_elo_after_a = match_data["elo_after_a"]

        # Now change Player A's start_elo to 1500
        update_resp = client.put(f"/players/{pa_id}", json={"start_elo": 1500})
        assert update_resp.status_code == 200
        assert update_resp.json()["start_elo"] == 1500

        # Refresh match data
        from app.models.match import Match
        db_session.expire_all()
        match = db_session.query(Match).filter(Match.id == match_data["id"]).first()

        # Elo values should have changed due to recalculation
        assert match.elo_before_a != original_elo_after_a or match.elo_after_a != original_elo_after_a
        # With higher start_elo, player A should have different Elo trajectory
        assert match.elo_before_a == 1500.0

    def test_changing_start_elo_updates_current_elo(self, client, db_session):
        """Changing start_elo should update player's current_elo via recalculation."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        # Create two players
        resp_a = client.post("/players/", json={"name": "Elo A", "start_elo": 1200})
        resp_b = client.post("/players/", json={"name": "Elo B", "start_elo": 1200})
        pa_id = resp_a.json()["id"]
        pb_id = resp_b.json()["id"]

        # Play a match
        client.post("/matches/", json={
            "date": "2025-06-01",
            "player_a_id": pa_id,
            "player_b_id": pb_id,
            "player1_score": 3,
            "player2_score": 0,
        })

        # Get current Elo before start_elo change
        pa_before = client.get(f"/players/{pa_id}").json()
        original_current_elo = pa_before["current_elo"]

        # Change start_elo
        client.put(f"/players/{pa_id}", json={"start_elo": 1400})

        # current_elo should be updated
        pa_after = client.get(f"/players/{pa_id}").json()
        assert pa_after["current_elo"] != original_current_elo

    def test_recalculation_after_start_elo_change_is_deterministic(self, client, db_session):
        """Recalculation should produce identical results on repeated runs."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        # Create players and match
        resp_a = client.post("/players/", json={"name": "Det A", "start_elo": 1200})
        resp_b = client.post("/players/", json={"name": "Det B", "start_elo": 1200})
        pa_id = resp_a.json()["id"]
        pb_id = resp_b.json()["id"]

        client.post("/matches/", json={
            "date": "2025-06-01",
            "player_a_id": pa_id,
            "player_b_id": pb_id,
            "player1_score": 3,
            "player2_score": 0,
        })

        # Change start_elo twice to same value
        client.put(f"/players/{pa_id}", json={"start_elo": 1300})
        first_elo = client.get(f"/players/{pa_id}").json()["current_elo"]

        client.put(f"/players/{pa_id}", json={"start_elo": 1300})
        second_elo = client.get(f"/players/{pa_id}").json()["current_elo"]

        # Should be identical (deterministic)
        assert first_elo == second_elo

    def test_audit_log_created_on_start_elo_change(self, client, db_session):
        """Changing start_elo should create RANKING_RECALCULATED audit entry."""
        from app.models.audit_log import AuditLog
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp_a = client.post("/players/", json={"name": "Audit A", "start_elo": 1200})
        resp_b = client.post("/players/", json={"name": "Audit B", "start_elo": 1200})
        pa_id = resp_a.json()["id"]
        pb_id = resp_b.json()["id"]

        # Create a match so recalculation has work to do
        client.post("/matches/", json={
            "date": "2025-06-01",
            "player_a_id": pa_id,
            "player_b_id": pb_id,
            "player1_score": 3,
            "player2_score": 0,
        })

        # Change start_elo
        client.put(f"/players/{pa_id}", json={"start_elo": 1500})

        # Check for RANKING_RECALCULATED audit entry
        logs = db_session.query(AuditLog).filter(
            AuditLog.action == "RANKING_RECALCULATED"
        ).all()
        assert len(logs) >= 1

    def test_no_recalculation_when_start_elo_unchanged(self, client, db_session):
        """Updating name without changing start_elo should NOT trigger recalculation."""
        from app.models.audit_log import AuditLog
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp = client.post("/players/", json={"name": "NameOnly", "start_elo": 1200})
        player_id = resp.json()["id"]

        # Count recalculation logs before
        logs_before = db_session.query(AuditLog).filter(
            AuditLog.action == "RANKING_RECALCULATED"
        ).count()

        # Update name only
        client.put(f"/players/{player_id}", json={"name": "NewName"})

        # Count recalculation logs after
        logs_after = db_session.query(AuditLog).filter(
            AuditLog.action == "RANKING_RECALCULATED"
        ).count()

        # Should be same count (no new recalculation)
        assert logs_after == logs_before
