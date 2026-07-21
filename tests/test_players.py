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
        assert player.active is True
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
        assert data["active"] is True
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