"""Tests for Alembic database migrations."""

import datetime

import sqlalchemy as sa
from sqlalchemy import create_engine, inspect
from alembic.config import Config
from alembic import command


class TestMigrations:
    """Test that Alembic migrations run cleanly on fresh and existing databases."""

    def _get_alembic_config(self) -> Config:
        """Create an Alembic config pointing to the test database."""
        alembic_cfg = Config("alembic.ini")
        return alembic_cfg

    def test_migration_upgrade_fresh_database(self, tmp_path):
        """Test that all migrations run on a fresh database (no tables)."""
        db_path = tmp_path / "fresh.db"
        db_url = f"sqlite:///{db_path}"

        engine = create_engine(db_url, connect_args={"check_same_thread": False})
        alembic_cfg = self._get_alembic_config()
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

        try:
            command.upgrade(alembic_cfg, "head")

            inspector = inspect(engine)
            tables = set(inspector.get_table_names())

            expected_tables = {
                "users",
                "players",
                "player_disable_periods",
                "matches",
                "club_settings",
                "audit_log",
                "alembic_version",
            }
            assert expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}"

            # Verify matches table has all columns including statistics
            columns = {col["name"] for col in inspector.get_columns("matches")}
            expected_cols = {
                "id",
                "date",
                "player_a_id",
                "player_b_id",
                "winner_id",
                "loser_id",
                "elo_before_a",
                "elo_before_b",
                "elo_after_a",
                "elo_after_b",
                "elo_change_a",
                "elo_change_b",
                "player1_score",
                "player2_score",
                "player_a_180s",
                "player_b_180s",
                "player_a_high_finishes",
                "player_b_high_finishes",
                "player_a_low_darts",
                "player_b_low_darts",
                "created_by",
                "created_at",
                "updated_at",
            }
            assert expected_cols.issubset(columns), (
                f"Missing columns in matches: {expected_cols - columns}"
            )

            # Fix #3 II: players table has the member-since entry_date column.
            player_cols = {col["name"] for col in inspector.get_columns("players")}
            assert "entry_date" in player_cols, f"Missing entry_date in players: {player_cols}"
        finally:
            engine.dispose()

    def test_migration_idempotent_on_existing_tables(self, tmp_path):
        """Test that migrations are idempotent when tables already exist."""
        db_path = tmp_path / "existing.db"
        db_url = f"sqlite:///{db_path}"

        engine = create_engine(db_url, connect_args={"check_same_thread": False})
        alembic_cfg = self._get_alembic_config()
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

        try:
            # First run: creates everything
            command.upgrade(alembic_cfg, "head")

            # Second run: should be a no-op (idempotent)
            command.upgrade(alembic_cfg, "head")

            inspector = inspect(engine)
            tables = set(inspector.get_table_names())
            assert "alembic_version" in tables
            assert "matches" in tables

            # Verify match statistics columns exist
            columns = {col["name"] for col in inspector.get_columns("matches")}
            assert "player_a_180s" in columns
            assert "player_b_180s" in columns
            assert "player_a_high_finishes" in columns
            assert "player_a_low_darts" in columns
        finally:
            engine.dispose()

    def test_stamp_then_upgrade(self, tmp_path):
        """Test stamp-then-upgrade scenario (pre-Alembic database)."""
        db_path = tmp_path / "pre_alembic.db"
        db_url = f"sqlite:///{db_path}"

        engine = create_engine(db_url, connect_args={"check_same_thread": False})
        alembic_cfg = self._get_alembic_config()
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

        try:
            # Create tables without Alembic (simulating pre-Alembic database)
            from app.core.database import Base

            Base.metadata.create_all(bind=engine)

            inspector = inspect(engine)
            tables = set(inspector.get_table_names())
            assert "matches" in tables
            assert "alembic_version" not in tables

            # Stamp as head (marks current state)
            command.stamp(alembic_cfg, "head")

            # Now alembic_version should exist
            inspector = inspect(engine)
            tables = set(inspector.get_table_names())
            assert "alembic_version" in tables

            # Running upgrade should be a no-op
            command.upgrade(alembic_cfg, "head")
        finally:
            engine.dispose()

    def test_disable_periods_backfilled_for_currently_disabled(self, tmp_path):
        """Fix #5: upgrading an existing database gives every currently
        disabled player an open disable period starting at the migration date,
        so their pre-migration history stays valid (nothing retroactive)."""
        db_path = tmp_path / "backfill.db"
        db_url = f"sqlite:///{db_path}"

        engine = create_engine(db_url, connect_args={"check_same_thread": False})
        alembic_cfg = self._get_alembic_config()
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

        try:
            # Run all migrations except the disable-period one.
            command.upgrade(alembic_cfg, "f5a6b7c8d9e0")

            with engine.begin() as conn:
                conn.execute(
                    sa.text(
                        "INSERT INTO players (name, start_elo, current_elo, active, disabled) "
                        "VALUES ('Old Disabled', 1200, 1200, 0, 1)"
                    )
                )
                conn.execute(
                    sa.text(
                        "INSERT INTO players (name, start_elo, current_elo, active, disabled) "
                        "VALUES ('Active Member', 1200, 1200, 1, 0)"
                    )
                )

            command.upgrade(alembic_cfg, "head")

            with engine.begin() as conn:
                rows = conn.execute(
                    sa.text(
                        "SELECT p.name, pd.disabled_from, pd.disabled_to "
                        "FROM player_disable_periods pd JOIN players p ON p.id = pd.player_id"
                    )
                ).mappings()

            periods = {r["name"]: r for r in rows}
            # Only the currently disabled player got a period.
            assert set(periods) == {"Old Disabled"}
            # It is an OPEN period (still disabled today) with a real start date.
            assert periods["Old Disabled"]["disabled_from"] is not None
            assert periods["Old Disabled"]["disabled_to"] is None
        finally:
            engine.dispose()

    def test_prune_zero_length_disable_periods(self, tmp_path):
        """The prune migration removes same-day (legacy) and empty at zero-length
        disable windows while keeping real multi-day windows and open rows."""
        db_path = tmp_path / "prune.db"
        db_url = f"sqlite:///{db_path}"

        engine = create_engine(db_url, connect_args={"check_same_thread": False})
        alembic_cfg = self._get_alembic_config()
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

        try:
            # Upgrade to the migration that creates the table.
            command.upgrade(alembic_cfg, "f6a7b8c9d0e1")

            today = datetime.date.today()
            yesterday = today - datetime.timedelta(days=1)
            past = today - datetime.timedelta(days=5)

            with engine.begin() as conn:
                conn.execute(
                    sa.text(
                        "INSERT INTO players (name, start_elo, current_elo, active, disabled) "
                        "VALUES ('SameDay', 1200, 1200, 1, 0)"
                    )
                )
                pid = conn.execute(
                    sa.text("SELECT id FROM players WHERE name = 'SameDay'")
                ).scalar()
                # Legacy same-day window (disabled_to == disabled_from) -> prune.
                conn.execute(
                    sa.text(
                        "INSERT INTO player_disable_periods (player_id, disabled_from, disabled_to) "
                        "VALUES (:pid, :day, :day)"
                    ),
                    {"pid": pid, "day": today},
                )
                # Empty window from an interim fix (disabled_to < disabled_from) -> prune.
                conn.execute(
                    sa.text(
                        "INSERT INTO player_disable_periods (player_id, disabled_from, disabled_to) "
                        "VALUES (:pid, :day, :yesterday)"
                    ),
                    {"pid": pid, "day": today, "yesterday": yesterday},
                )
                # Genuine multi-day window -> keep.
                conn.execute(
                    sa.text(
                        "INSERT INTO player_disable_periods (player_id, disabled_from, disabled_to) "
                        "VALUES (:pid, :past, :yesterday)"
                    ),
                    {"pid": pid, "past": past, "yesterday": yesterday},
                )
                # Open window (still disabled) -> keep.
                conn.execute(
                    sa.text(
                        "INSERT INTO player_disable_periods (player_id, disabled_from, disabled_to) "
                        "VALUES (:pid, :day, NULL)"
                    ),
                    {"pid": pid, "day": today},
                )

            command.upgrade(alembic_cfg, "head")

            with engine.begin() as conn:
                rows = conn.execute(
                    sa.text(
                        "SELECT disabled_from, disabled_to FROM player_disable_periods "
                        "ORDER BY disabled_from, disabled_to"
                    )
                ).fetchall()

            # Only the multi-day window and the open window survive.
            # (SQLite DATE columns come back as ISO strings.)
            expected = {
                (today.isoformat(), None),  # open (still disabled) kept
                (past.isoformat(), yesterday.isoformat()),  # multi-day kept
            }
            assert {tuple(r) for r in rows} == expected, rows
        finally:
            engine.dispose()

    def test_init_db_fresh_database(self, tmp_path, monkeypatch):
        """Test init_db() on a fresh database."""
        db_path = tmp_path / "init_fresh.db"
        db_url = f"sqlite:///{db_path}"

        monkeypatch.setenv("DATABASE_URL", db_url)

        # We can't easily test the full init_db() because it uses the global engine,
        # but we can test the create_all + stamp logic directly
        engine = create_engine(db_url, connect_args={"check_same_thread": False})
        from app.core.database import Base

        # Scenario 1: Fresh database
        inspector = inspect(engine)
        assert not inspector.get_table_names()

        Base.metadata.create_all(bind=engine)
        alembic_cfg = self._get_alembic_config()
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        command.stamp(alembic_cfg, "head")

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert "alembic_version" in tables
        assert "matches" in tables
        assert "users" in tables
        assert "players" in tables

        engine.dispose()

    def test_matches_table_has_statistics_columns(self, tmp_path):
        """Test that the matches table has all dart statistics columns after migration."""
        db_path = tmp_path / "stats.db"
        db_url = f"sqlite:///{db_path}"

        engine = create_engine(db_url, connect_args={"check_same_thread": False})
        alembic_cfg = self._get_alembic_config()
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

        try:
            command.upgrade(alembic_cfg, "head")

            inspector = inspect(engine)
            columns = {col["name"] for col in inspector.get_columns("matches")}

            # Score columns
            assert "player1_score" in columns
            assert "player2_score" in columns

            # Statistics columns
            assert "player_a_180s" in columns
            assert "player_b_180s" in columns
            assert "player_a_high_finishes" in columns
            assert "player_b_high_finishes" in columns
            assert "player_a_low_darts" in columns
            assert "player_b_low_darts" in columns
        finally:
            engine.dispose()

    def test_player_entry_date_migration_backfills_existing_rows(self, tmp_path):
        """Fix #3 II: the migration adds entry_date and backfills it to
        min(creation date, first recorded match date)."""
        from sqlalchemy import text

        db_path = tmp_path / "entry.db"
        db_url = f"sqlite:///{db_path}"

        engine = create_engine(db_url, connect_args={"check_same_thread": False})
        alembic_cfg = self._get_alembic_config()
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

        try:
            # Old head: players/matches exist WITHOUT entry_date.
            command.upgrade(alembic_cfg, "e3f0b5d6c7a8")

            with engine.begin() as conn:
                for name in ("LegacyA", "LegacyB", "Newbie"):
                    conn.execute(
                        text(
                            "INSERT INTO players "
                            "(name, start_elo, current_elo, active, disabled, created_at, updated_at) "
                            "VALUES (:name, 1200, 1200, 1, 0, '2026-07-24 12:00:00', '2026-07-24 12:00:00')"
                        ),
                        {"name": name},
                    )
                # A historical match on 2026-05-06 (LegacyA vs LegacyB) BEFORE
                # the bulk import date - the import scenario from the live DB.
                conn.execute(
                    text(
                        "INSERT INTO matches "
                        "(date, player_a_id, player_b_id, winner_id, loser_id, "
                        "elo_before_a, elo_before_b, elo_after_a, elo_after_b, "
                        "elo_change_a, elo_change_b, created_at, updated_at, "
                        "player_a_180s, player_b_180s, best_of_legs, k_factor) "
                        "VALUES ('2026-05-06', 1, 2, 1, 2, 1200, 1200, 1216, 1184, "
                        "16, -16, '2026-07-24 12:00:00', '2026-07-24 12:00:00', 0, 0, 5, 32.0)"
                    )
                )

            command.upgrade(alembic_cfg, "head")

            with engine.connect() as conn:
                rows = conn.execute(
                    text("SELECT name, entry_date FROM players ORDER BY id")
                ).mappings()
                by_name = {r["name"]: str(r["entry_date"]) for r in rows}

            # Players with a match: backfilled to the earliest match date.
            assert by_name["LegacyA"] == "2026-05-06"
            assert by_name["LegacyB"] == "2026-05-06"
            # Never-played player: backfilled to the creation date.
            assert by_name["Newbie"] == "2026-07-24"
        finally:
            engine.dispose()

    def test_init_db_raises_runtimeerror_when_upgrade_fails(self, tmp_path, monkeypatch):
        """Scenario 2 (tracked DB): a failed Alembic upgrade must abort startup (Fix M2).

        Previously ``init_db()`` only logged the error and let the app continue
        on an un-migrated schema. Now it must raise so the process exits with a
        non-zero status and the orchestrator can restart it.
        """
        import pytest
        from sqlalchemy import text
        import app.core.database as db_module
        from alembic import command as alembic_command

        db_path = tmp_path / "stale_tracked.db"
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        try:
            # Pre-stage an Alembic-tracked database: only the alembic_version
            # table exists, which routes init_db() into scenario 2 (upgrade).
            with engine.begin() as conn:
                conn.execute(
                    text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
                )
                conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('base')"))

            def boom_upgrade(cfg, revision):
                raise RuntimeError("migration boom")

            monkeypatch.setattr(db_module, "engine", engine)
            monkeypatch.setattr(alembic_command, "upgrade", boom_upgrade)

            with pytest.raises(RuntimeError, match="Alembic upgrade failed"):
                db_module.init_db()
        finally:
            engine.dispose()

    def test_init_db_raises_runtimeerror_when_stamp_fails(self, tmp_path, monkeypatch):
        """Scenario 3 (pre-Alembic DB): a failed stamp/upgrade must abort startup (Fix M2)."""
        import pytest
        from sqlalchemy import text
        import app.core.database as db_module
        from alembic import command as alembic_command

        db_path = tmp_path / "pre_alembic.db"
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        try:
            # Pre-Alembic database: tables exist but no alembic_version table,
            # which routes init_db() into scenario 3 (stamp then upgrade).
            with engine.begin() as conn:
                conn.execute(
                    text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(50))")
                )

            def boom_stamp(cfg, revision):
                raise RuntimeError("stamp boom")

            monkeypatch.setattr(db_module, "engine", engine)
            monkeypatch.setattr(alembic_command, "stamp", boom_stamp)

            with pytest.raises(RuntimeError, match="Alembic stamp/upgrade failed"):
                db_module.init_db()
        finally:
            engine.dispose()
