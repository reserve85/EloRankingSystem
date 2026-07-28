"""Tests for centralized configuration handling."""

import os

import yaml

from app.core.config import (
    Settings,
    _yaml_to_env_defaults,
    get_settings,
    load_yaml_config,
)


class TestLoadYamlConfig:
    """Tests for YAML config file loading."""

    def test_load_existing_yaml(self, tmp_path):
        """Test loading a valid YAML config file."""
        config_data = {
            "app": {"name": "Test Club", "environment": "production"},
            "elo": {"default_rating": 1500, "k_factor": 24},
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        result = load_yaml_config(str(config_file))
        assert result["app"]["name"] == "Test Club"
        assert result["elo"]["default_rating"] == 1500

    def test_load_missing_yaml(self, tmp_path):
        """Test loading a non-existent YAML file returns empty dict."""
        result = load_yaml_config(str(tmp_path / "nonexistent.yaml"))
        assert result == {}

    def test_load_empty_yaml(self, tmp_path):
        """Test loading an empty YAML file returns empty dict."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("", encoding="utf-8")

        result = load_yaml_config(str(config_file))
        assert result == {}

    def test_load_yaml_with_all_sections(self, tmp_path):
        """Test loading YAML with all configuration sections."""
        config_data = {
            "app": {
                "name": "My Club",
                "environment": "production",
                "debug": False,
            },
            "elo": {
                "default_rating": 1300,
                "k_factor": 40,
            },
            "ranking": {
                "inactivity_months": 6,
            },
            "system_user": {
                "username": "admin",
                "password": "secret123",
            },
            "security": {
                "jwt_secret": "my-secret-key",
                "jwt_algorithm": "HS256",
                "access_token_lifetime_minutes": 600,
                "cookie_secure": True,
                "cookie_httponly": True,
                "cookie_samesite": "strict",
            },
            "storage": {
                "data_dir": "/custom/data",
                "upload_dir": "/custom/uploads",
                "log_dir": "/custom/logs",
                "backup_dir": "/custom/backups",
            },
        }
        config_file = tmp_path / "full_config.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        result = load_yaml_config(str(config_file))
        assert len(result) == 6
        assert result["app"]["name"] == "My Club"
        assert result["elo"]["default_rating"] == 1300
        assert result["ranking"]["inactivity_months"] == 6
        assert result["security"]["jwt_secret"] == "my-secret-key"


class TestYamlToEnvDefaults:
    """Tests for YAML to environment variable mapping."""

    def test_empty_config(self):
        """Test with empty YAML config."""
        result = _yaml_to_env_defaults({})
        assert result == {}

    def test_app_section_mapping(self):
        """Test app section YAML → env var mapping."""
        yaml_config = {
            "app": {
                "name": "Test Club",
                "environment": "production",
                "debug": True,
            }
        }
        result = _yaml_to_env_defaults(yaml_config)
        assert result["APP_NAME"] == "Test Club"
        assert result["APP_ENV"] == "production"
        assert result["APP_DEBUG"] == "True"

    def test_elo_section_mapping(self):
        """Test elo section YAML → env var mapping."""
        yaml_config = {
            "elo": {"default_rating": 1500, "k_factor": 24}
        }
        result = _yaml_to_env_defaults(yaml_config)
        assert result["DEFAULT_ELO"] == "1500"
        assert result["K_FACTOR"] == "24"

    def test_ranking_section_mapping(self):
        """Test ranking section YAML → env var mapping."""
        yaml_config = {"ranking": {"inactivity_months": 6}}
        result = _yaml_to_env_defaults(yaml_config)
        assert result["INACTIVITY_MONTHS"] == "6"

    def test_system_user_section_mapping(self):
        """Test system_user section YAML → env var mapping."""
        yaml_config = {
            "system_user": {"username": "admin", "password": "secret"}
        }
        result = _yaml_to_env_defaults(yaml_config)
        assert result["SYSTEM_USER_USERNAME"] == "admin"
        assert result["SYSTEM_USER_PASSWORD"] == "secret"

    def test_security_section_mapping(self):
        """Test security section YAML → env var mapping."""
        yaml_config = {
            "security": {
                "jwt_secret": "my-key",
                "jwt_algorithm": "HS512",
                "access_token_lifetime_minutes": 600,
                "cookie_secure": True,
                "cookie_httponly": False,
                "cookie_samesite": "strict",
            }
        }
        result = _yaml_to_env_defaults(yaml_config)
        assert result["JWT_SECRET"] == "my-key"
        assert result["JWT_ALGORITHM"] == "HS512"
        assert result["ACCESS_TOKEN_LIFETIME_MINUTES"] == "600"
        assert result["COOKIE_SECURE"] == "True"
        assert result["COOKIE_HTTPONLY"] == "False"
        assert result["COOKIE_SAMESITE"] == "strict"

    def test_storage_section_mapping(self):
        """Test storage section YAML → env var mapping."""
        yaml_config = {
            "storage": {
                "data_dir": "/custom/data",
                "upload_dir": "/custom/uploads",
                "log_dir": "/custom/logs",
            }
        }
        result = _yaml_to_env_defaults(yaml_config)
        assert result["DATA_DIR"] == "/custom/data"
        assert result["UPLOAD_DIR"] == "/custom/uploads"
        assert result["LOG_DIR"] == "/custom/logs"

    def test_env_vars_not_overwritten(self, monkeypatch):
        """Test that existing env vars are NOT overwritten by YAML."""
        monkeypatch.setenv("APP_NAME", "Env Club")
        yaml_config = {"app": {"name": "YAML Club"}}
        result = _yaml_to_env_defaults(yaml_config)
        assert "APP_NAME" not in result

    def test_partial_config(self):
        """Test with only some sections present in YAML."""
        yaml_config = {"elo": {"default_rating": 1500}}
        result = _yaml_to_env_defaults(yaml_config)
        assert result == {"DEFAULT_ELO": "1500"}

    def test_unknown_sections_ignored(self):
        """Test that unknown YAML sections are safely ignored."""
        yaml_config = {"unknown_section": {"key": "value"}}
        result = _yaml_to_env_defaults(yaml_config)
        assert result == {}


class TestSettings:
    """Tests for the Settings class defaults."""

    def test_default_app_settings(self):
        """Test app settings defaults."""
        settings = Settings()
        assert settings.app_name == "Elo Ranking System"
        assert settings.app_env == "development"
        assert settings.app_debug is False

    def test_default_elo_settings(self):
        """Test Elo settings defaults."""
        settings = Settings()
        assert settings.default_elo == 1200
        assert settings.k_factor == 32

    def test_default_ranking_settings(self):
        """Test ranking settings defaults."""
        settings = Settings()
        assert settings.inactivity_months == 3

    def test_default_system_user_settings(self):
        """Test system user settings defaults."""
        settings = Settings()
        assert settings.system_user_username == "system"
        assert settings.system_user_password == "change_me"

    def test_default_security_settings(self):
        """Test security settings defaults."""
        settings = Settings()
        assert settings.jwt_secret == "change_me"
        assert settings.jwt_algorithm == "HS256"
        assert settings.access_token_lifetime_minutes == 480
        assert settings.cookie_secure is False
        assert settings.cookie_httponly is True
        assert settings.cookie_samesite == "lax"

    def test_default_storage_settings(self):
        """Test storage settings defaults."""
        settings = Settings()
        assert "data" in settings.data_dir
        assert "uploads" in settings.upload_dir
        assert "logs" in settings.log_dir

    def test_default_database_url(self):
        """Test default database URL contains sqlite."""
        settings = Settings()
        assert "sqlite" in settings.database_url

    def test_settings_from_env_vars(self, monkeypatch):
        """Test settings override from environment variables."""
        monkeypatch.setenv("APP_NAME", "Env Club")
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("APP_DEBUG", "true")
        monkeypatch.setenv("DEFAULT_ELO", "1500")
        monkeypatch.setenv("K_FACTOR", "24")
        monkeypatch.setenv("INACTIVITY_MONTHS", "6")
        monkeypatch.setenv("JWT_SECRET", "env-secret")
        monkeypatch.setenv("COOKIE_SECURE", "true")

        settings = Settings()
        assert settings.app_name == "Env Club"
        assert settings.app_env == "production"
        assert settings.app_debug is True
        assert settings.default_elo == 1500
        assert settings.k_factor == 24
        assert settings.inactivity_months == 6
        assert settings.jwt_secret == "env-secret"
        assert settings.cookie_secure is True


class TestGetSettings:
    """Tests for the get_settings factory function."""

    def test_get_settings_with_yaml(self, tmp_path):
        """Test get_settings loads YAML config."""
        config_data = {
            "app": {"name": "YAML Club"},
            "elo": {"default_rating": 1400, "k_factor": 28},
            "ranking": {"inactivity_months": 4},
        }
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        # Clean env vars that might interfere
        env_vars_to_clean = ["APP_NAME", "DEFAULT_ELO", "K_FACTOR", "INACTIVITY_MONTHS"]
        saved = {}
        for var in env_vars_to_clean:
            saved[var] = os.environ.pop(var, None)

        try:
            s = get_settings(str(config_file))
            assert s.app_name == "YAML Club"
            assert s.default_elo == 1400
            assert s.k_factor == 28
            assert s.inactivity_months == 4
        finally:
            # Restore env vars
            for var, val in saved.items():
                if val is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = val

    def test_get_settings_without_yaml(self, tmp_path):
        """Test get_settings with non-existent YAML uses defaults."""
        s = get_settings(str(tmp_path / "nonexistent.yaml"))
        assert s.app_name == "Elo Ranking System"
        assert s.default_elo == 1200
        assert s.k_factor == 32

    def test_get_settings_env_overrides_yaml(self, tmp_path, monkeypatch):
        """Test that env vars take precedence over YAML config."""
        config_data = {"app": {"name": "YAML Club"}}
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        monkeypatch.setenv("APP_NAME", "Env Club")
        s = get_settings(str(config_file))
        assert s.app_name == "Env Club"

    def test_get_settings_full_config(self, tmp_path):
        """Test get_settings with complete YAML config."""
        config_data = {
            "app": {"name": "Full Club", "environment": "staging", "debug": True},
            "elo": {"default_rating": 1350, "k_factor": 36},
            "ranking": {"inactivity_months": 5},
            "system_user": {"username": "root", "password": "strong_pass"},
            "security": {
                "jwt_secret": "full-secret",
                "jwt_algorithm": "HS512",
                "access_token_lifetime_minutes": 300,
                "cookie_secure": True,
                "cookie_httponly": True,
                "cookie_samesite": "strict",
            },
            "storage": {
                "data_dir": "/srv/data",
                "upload_dir": "/srv/uploads",
                "log_dir": "/srv/logs",
                "backup_dir": "/srv/backups",
            },
        }
        config_file = tmp_path / "full_config.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        # Clean all relevant env vars
        env_vars = [
            "APP_NAME", "APP_ENV", "APP_DEBUG", "DEFAULT_ELO", "K_FACTOR",
            "INACTIVITY_MONTHS", "SYSTEM_USER_USERNAME", "SYSTEM_USER_PASSWORD",
            "JWT_SECRET", "JWT_ALGORITHM", "ACCESS_TOKEN_LIFETIME_MINUTES",
            "COOKIE_SECURE", "COOKIE_HTTPONLY", "COOKIE_SAMESITE",
            "DATA_DIR", "UPLOAD_DIR", "LOG_DIR", "BACKUP_DIR",
        ]
        saved = {}
        for var in env_vars:
            saved[var] = os.environ.pop(var, None)

        try:
            s = get_settings(str(config_file))
            assert s.app_name == "Full Club"
            assert s.app_env == "staging"
            assert s.app_debug is True
            assert s.default_elo == 1350
            assert s.k_factor == 36
            assert s.inactivity_months == 5
            assert s.system_user_username == "root"
            assert s.system_user_password == "strong_pass"
            assert s.jwt_secret == "full-secret"
            assert s.jwt_algorithm == "HS512"
            assert s.access_token_lifetime_minutes == 300
            assert s.cookie_secure is True
            assert s.cookie_httponly is True
            assert s.cookie_samesite == "strict"
            assert "/srv/data" in s.data_dir
            assert "/srv/uploads" in s.upload_dir
            assert "/srv/logs" in s.log_dir
        finally:
            for var, val in saved.items():
                if val is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = val


class TestSettingsTypes:
    """Tests for Settings type coercion."""

    def test_bool_from_string_true(self, monkeypatch):
        """Test boolean parsing from 'true' string."""
        monkeypatch.setenv("APP_DEBUG", "true")
        s = Settings()
        assert s.app_debug is True

    def test_bool_from_string_false(self, monkeypatch):
        """Test boolean parsing from 'false' string."""
        monkeypatch.setenv("APP_DEBUG", "false")
        s = Settings()
        assert s.app_debug is False

    def test_int_from_string(self, monkeypatch):
        """Test integer parsing from string env var."""
        monkeypatch.setenv("K_FACTOR", "48")
        s = Settings()
        assert s.k_factor == 48
        assert isinstance(s.k_factor, int)

    def test_string_fields(self):
        """Test string fields are strings."""
        s = Settings()
        assert isinstance(s.app_name, str)
        assert isinstance(s.jwt_algorithm, str)
        assert isinstance(s.cookie_samesite, str)

    def test_date_format_default(self):
        """Test default date format is dd/MM/yyyy."""
        s = Settings()
        assert s.date_format == "dd/MM/yyyy"

    def test_date_format_from_env(self, monkeypatch):
        """Test date format can be set via env var."""
        monkeypatch.setenv("DATE_FORMAT", "yyyy-MM-dd")
        s = Settings()
        assert s.date_format == "yyyy-MM-dd"

    def test_timezone_default(self):
        """Test default timezone is UTC."""
        s = Settings()
        assert s.timezone == "UTC"
