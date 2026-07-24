"""Centralized configuration handling for the Elo Ranking System.

Configuration loading priority (highest to lowest):
1. Environment variables
2. .env file values
3. config.yaml values
4. Default values defined in Settings class
"""

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings


# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent.parent


def load_yaml_config(config_path: Optional[str] = None) -> dict:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config.yaml. If None, uses CONFIG_PATH env var
                     or falls back to {BASE_DIR}/config.yaml.

    Returns:
        Parsed YAML config dict, or empty dict if file not found.
    """
    if config_path is None:
        config_path = os.getenv("CONFIG_PATH", str(BASE_DIR / "config.yaml"))

    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _yaml_to_env_defaults(yaml_config: dict) -> dict[str, str]:
    """Extract environment variable defaults from YAML config sections.

    Maps YAML config keys to environment variable names.
    Only returns values for keys NOT already set in the environment.

    Args:
        yaml_config: Parsed YAML config dict.

    Returns:
        Dict of env_var_name -> value for keys to set as os.environ defaults.
    """
    if not yaml_config:
        return {}

    env_defaults: dict[str, str] = {}

    # Mapping: (yaml_section, yaml_key, env_var_name)
    mappings = [
        ("app", "name", "APP_NAME"),
        ("app", "club_name", "CLUB_NAME"),
        ("app", "environment", "APP_ENV"),
        ("app", "debug", "APP_DEBUG"),
        ("app", "base_url", "APP_BASE_URL"),
        ("elo", "default_rating", "DEFAULT_ELO"),
        ("elo", "k_factor", "K_FACTOR"),
        ("ranking", "inactivity_months", "INACTIVITY_MONTHS"),
        ("legal", "contact_company", "CONTACT_COMPANY"),
        ("legal", "contact_name", "CONTACT_NAME"),
        ("legal", "contact_street", "CONTACT_STREET"),
        ("legal", "contact_city", "CONTACT_CITY"),
        ("legal", "contact_email", "CONTACT_EMAIL"),
        ("statistics", "high_finish_min", "HIGH_FINISH_MIN"),
        ("statistics", "high_finish_max", "HIGH_FINISH_MAX"),
        ("statistics", "low_darts_min", "LOW_DARTS_MIN"),
        ("statistics", "low_darts_max", "LOW_DARTS_MAX"),
        ("statistics", "best_of_legs", "BEST_OF_LEGS"),
        ("system_user", "username", "SYSTEM_USER_USERNAME"),
        ("system_user", "password", "SYSTEM_USER_PASSWORD"),
        ("app", "timezone", "TIMEZONE"),
        ("app", "date_format", "DATE_FORMAT"),
        ("security", "jwt_secret", "JWT_SECRET"),
        ("security", "jwt_algorithm", "JWT_ALGORITHM"),
        ("security", "access_token_lifetime_minutes", "ACCESS_TOKEN_LIFETIME_MINUTES"),
        ("security", "cookie_secure", "COOKIE_SECURE"),
        ("security", "cookie_httponly", "COOKIE_HTTPONLY"),
        ("security", "cookie_samesite", "COOKIE_SAMESITE"),
        ("storage", "data_dir", "DATA_DIR"),
        ("storage", "upload_dir", "UPLOAD_DIR"),
        ("storage", "log_dir", "LOG_DIR"),
        ("storage", "backup_dir", "BACKUP_DIR"),
    ]

    for section, key, env_var in mappings:
        section_data = yaml_config.get(section, {})
        if isinstance(section_data, dict) and key in section_data:
            value = section_data[key]
            # Only set if not already in environment (env vars take precedence)
            if env_var not in os.environ:
                env_defaults[env_var] = str(value)

    return env_defaults


class Settings(BaseSettings):
    """Application settings with typed fields and defaults.

    Values are resolved from: env vars > .env file > YAML config > defaults.
    """

    # ── App ──────────────────────────────────────────────
    app_name: str = Field(default="Elo Ranking System", alias="APP_NAME")
    club_name: str = Field(default="", alias="CLUB_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=False, alias="APP_DEBUG")
    app_base_url: str = Field(default="", alias="APP_BASE_URL")

    # ── Database ─────────────────────────────────────────
    database_url: str = Field(
        default=f"sqlite:///{BASE_DIR / 'data' / 'database.db'}",
        alias="DATABASE_URL",
    )

    # ── Elo ──────────────────────────────────────────────
    default_elo: int = Field(default=1200, alias="DEFAULT_ELO")
    k_factor: int = Field(default=32, alias="K_FACTOR")

    # ── Ranking ──────────────────────────────────────────
    inactivity_months: int = Field(default=3, alias="INACTIVITY_MONTHS")

    # ── Legal / Impressum ─────────────────────────────────
    contact_company: str = Field(default="Company", alias="CONTACT_COMPANY")
    contact_name: str = Field(default="Max Mustermann", alias="CONTACT_NAME")
    contact_street: str = Field(default="Musterstrasse 1", alias="CONTACT_STREET")
    contact_city: str = Field(default="11111 Musterstadt", alias="CONTACT_CITY")
    contact_email: str = Field(default="max.Mustermann@Muster.mu", alias="CONTACT_EMAIL")

    # ── Statistics ────────────────────────────────────────
    high_finish_min: int = Field(default=100, alias="HIGH_FINISH_MIN")
    high_finish_max: int = Field(default=170, alias="HIGH_FINISH_MAX")
    low_darts_min: int = Field(default=9, alias="LOW_DARTS_MIN")
    low_darts_max: int = Field(default=21, alias="LOW_DARTS_MAX")
    best_of_legs: int = Field(default=5, alias="BEST_OF_LEGS")

    # ── System User ──────────────────────────────────────
    system_user_username: str = Field(
        default="system", alias="SYSTEM_USER_USERNAME"
    )
    system_user_password: str = Field(
        default="change_me", alias="SYSTEM_USER_PASSWORD"
    )

    # ── Security ─────────────────────────────────────────
    jwt_secret: str = Field(default="change_me", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_lifetime_minutes: int = Field(
        default=480, alias="ACCESS_TOKEN_LIFETIME_MINUTES"
    )
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    cookie_httponly: bool = Field(default=True, alias="COOKIE_HTTPONLY")
    cookie_samesite: str = Field(default="lax", alias="COOKIE_SAMESITE")

    # ── Timezone & Date Format
    timezone: str = Field(default="UTC", alias="TIMEZONE")
    date_format: str = Field(default="dd/MM/yyyy", alias="DATE_FORMAT")

    # ── Storage ──────────────────────────────────────────
    data_dir: str = Field(default=str(BASE_DIR / "data"), alias="DATA_DIR")
    upload_dir: str = Field(
        default=str(BASE_DIR / "uploads"), alias="UPLOAD_DIR"
    )
    log_dir: str = Field(default=str(BASE_DIR / "logs"), alias="LOG_DIR")
    backup_dir: str = Field(
        default=str(BASE_DIR / "backups"), alias="BACKUP_DIR"
    )

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
    )


def get_settings(yaml_path: Optional[str] = None) -> Settings:
    """Create and return application settings.

    Loads YAML config first as environment defaults, then creates Settings
    which reads .env and env vars via pydantic-settings.

    Args:
        yaml_path: Optional explicit path to config.yaml.
                   Defaults to CONFIG_PATH env var or {BASE_DIR}/config.yaml.

    Returns:
        Fully resolved Settings instance.
    """
    yaml_config = load_yaml_config(yaml_path)

    # Set YAML values as env var defaults (env vars / .env take precedence)
    env_defaults = _yaml_to_env_defaults(yaml_config)
    for key, value in env_defaults.items():
        os.environ.setdefault(key, value)

    return Settings()


# Singleton settings instance
settings = get_settings()
