"""Tests for Alembic database migrations."""

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
