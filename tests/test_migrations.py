"""Tests for Alembic database migrations."""

import os
import pytest
from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
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

            expected_tables = {"users", "players", "matches", "club_settings", "audit_log", "alembic_version"}
            assert expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}"

            # Verify matches table has all columns including statistics
            columns = {col["name"] for col in inspector.get_columns("matches")}
            expected_cols = {
                "id", "date", "player_a_id", "player_b_id",
                "winner_id", "loser_id",
                "elo_before_a", "elo_before_b", "elo_after_a", "elo_after_b",
                "elo_change_a", "elo_change_b",
                "player1_score", "player2_score",
                "player_a_180s", "player_b_180s",
                "player_a_high_finishes", "player_b_high_finishes",
                "player_a_low_darts", "player_b_low_darts",
                "created_by", "created_at", "updated_at",
            }
            assert expected_cols.issubset(columns), f"Missing columns in matches: {expected_cols - columns}"
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