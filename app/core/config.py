"""Centralized configuration handling for the Elo Ranking System."""

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic_settings import BaseSettings
from pydantic import Field


# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent.parent


def load_yaml_config(config_path: Optional[str] = None) -> dict:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = os.getenv("CONFIG_PATH", str(BASE_DIR / "config.yaml"))

    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class Settings(BaseSettings):
    """Application settings loaded from environment variables and config files."""

    # App
    app_name: str = Field(default="Elo Ranking System", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=False, alias="APP_DEBUG")

    # Database
    database_url: str = Field(
        default=f"sqlite:///{BASE_DIR / 'data' / 'database.db'}",
        alias="DATABASE_URL",
    )

    # Security
    jwt_secret: str = Field(default="change_me", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_lifetime_minutes: int = Field(
        default=480, alias="ACCESS_TOKEN_LIFETIME_MINUTES"
    )
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    cookie_httponly: bool = Field(default=True, alias="COOKIE_HTTPONLY")
    cookie_samesite: str = Field(default="lax", alias="COOKIE_SAMESITE")

    # System User
    system_user_username: str = Field(default="system", alias="SYSTEM_USER_USERNAME")
    system_user_password: str = Field(default="change_me", alias="SYSTEM_USER_PASSWORD")

    # Elo
    default_elo: int = 1200
    k_factor: int = 32

    # Ranking
    inactivity_months: int = 3

    # Storage
    data_dir: str = Field(
        default=str(BASE_DIR / "data"), alias="DATA_DIR"
    )
    upload_dir: str = Field(
        default=str(BASE_DIR / "uploads"), alias="UPLOAD_DIR"
    )
    log_dir: str = Field(
        default=str(BASE_DIR / "logs"), alias="LOG_DIR"
    )
    backup_dir: str = Field(
        default=str(BASE_DIR / "backups"), alias="BACKUP_DIR"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        populate_by_name = True


def get_settings() -> Settings:
    """Create and return application settings, merging YAML config with env vars."""
    yaml_config = load_yaml_config()

    # Merge YAML values as defaults (env vars take precedence)
    env_overrides = {}

    if yaml_config:
        app_config = yaml_config.get("app", {})
        elo_config = yaml_config.get("elo", {})
        ranking_config = yaml_config.get("ranking", {})
        security_config = yaml_config.get("security", {})
        system_config = yaml_config.get("system_user", {})
        storage_config = yaml_config.get("storage", {})

        env_overrides = {
            "APP_NAME": app_config.get("name", "Elo Ranking System"),
            "APP_ENV": app_config.get("environment", "development"),
            "APP_DEBUG": str(app_config.get("debug", False)).lower(),
        }

        # Only set if not already in environment
        for key, value in env_overrides.items():
            if key not in os.environ:
                os.environ[key] = str(value)

        # Store Elo and ranking config for later use
        if "default_elo" not in os.environ and elo_config.get("default_rating"):
            os.environ["default_elo"] = str(elo_config["default_rating"])
        if "k_factor" not in os.environ and elo_config.get("k_factor"):
            os.environ["k_factor"] = str(elo_config["k_factor"])
        if "inactivity_months" not in os.environ and ranking_config.get("inactivity_months"):
            os.environ["inactivity_months"] = str(ranking_config["inactivity_months"])

    settings = Settings()

    # Apply YAML-only values that don't have env var mappings
    if yaml_config:
        elo_config = yaml_config.get("elo", {})
        ranking_config = yaml_config.get("ranking", {})

        if "default_rating" in elo_config:
            settings.default_elo = elo_config["default_rating"]
        if "k_factor" in elo_config:
            settings.k_factor = elo_config["k_factor"]
        if "inactivity_months" in ranking_config:
            settings.inactivity_months = ranking_config["inactivity_months"]

    return settings


# Singleton settings instance
settings = get_settings()