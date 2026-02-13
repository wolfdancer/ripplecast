"""Tests for YAML configuration loading."""

import os
from pathlib import Path

import pytest

from ripplecast.config import (
    AccountConfig,
    Config,
    ConfigurationError,
    Settings,
    get_config,
    reload_config,
)


@pytest.fixture
def sample_yaml_config(tmp_path):
    """Create a sample YAML config file."""
    config_content = """
settings:
  log-level: DEBUG

accounts:
  - name: test-mastodon
    platform: mastodon
    enabled: true
    credentials:
      instance-url: https://mastodon.social
      access-token: test_token

  - name: test-bluesky
    platform: bluesky
    enabled: true
    credentials:
      handle: test.bsky.social
      app-password: xxxx-xxxx-xxxx-xxxx
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)
    return config_file


@pytest.fixture
def minimal_yaml_config(tmp_path):
    """Create a minimal valid YAML config file."""
    config_content = """
accounts:
  - name: my-bluesky
    platform: bluesky
    credentials:
      handle: user.bsky.social
      app-password: test-password
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)
    return config_file


class TestAccountConfig:
    """Tests for AccountConfig dataclass."""

    def test_get_platform_config_mastodon(self):
        """Test converting AccountConfig to MastodonConfig."""
        account = AccountConfig(
            name="test-mastodon",
            platform="mastodon",
            credentials={
                "instance-url": "https://example.social",
                "access-token": "token123",
            },
        )
        config = account.get_platform_config()
        assert config.instance_url == "https://example.social"
        assert config.access_token == "token123"
        assert config.is_configured

    def test_get_platform_config_bluesky(self):
        """Test converting AccountConfig to BlueskyConfig."""
        account = AccountConfig(
            name="test-bluesky",
            platform="bluesky",
            credentials={
                "handle": "user.bsky.social",
                "app-password": "pass123",
            },
        )
        config = account.get_platform_config()
        assert config.handle == "user.bsky.social"
        assert config.app_password == "pass123"
        assert config.is_configured

    def test_get_platform_config_unknown_platform(self):
        """Test that unknown platform raises ValueError."""
        account = AccountConfig(
            name="test",
            platform="twitter",
            credentials={},
        )
        with pytest.raises(ValueError, match="Unknown platform"):
            account.get_platform_config()

    def test_enabled_default_true(self):
        """Test that enabled defaults to True."""
        account = AccountConfig(
            name="test",
            platform="bluesky",
            credentials={},
        )
        assert account.enabled is True


class TestYamlLoading:
    """Tests for loading YAML configuration."""

    def test_load_valid_yaml(self, sample_yaml_config):
        """Test loading a valid YAML config."""
        config = Config.from_yaml(sample_yaml_config)

        assert len(config.accounts) == 2
        assert config.settings.log_level == "DEBUG"
        assert config.log_level == "DEBUG"

        # Check first account
        mastodon = config.accounts[0]
        assert mastodon.name == "test-mastodon"
        assert mastodon.platform == "mastodon"
        assert mastodon.enabled is True
        assert mastodon.credentials["instance-url"] == "https://mastodon.social"

        # Check second account
        bluesky = config.accounts[1]
        assert bluesky.name == "test-bluesky"
        assert bluesky.platform == "bluesky"
        assert bluesky.credentials["handle"] == "test.bsky.social"

    def test_load_minimal_yaml(self, minimal_yaml_config):
        """Test loading minimal YAML with defaults."""
        config = Config.from_yaml(minimal_yaml_config)

        assert len(config.accounts) == 1
        assert config.settings.log_level == "INFO"  # Default
        assert config.accounts[0].enabled is True  # Default

    def test_disabled_account(self, tmp_path):
        """Test that disabled accounts are loaded correctly."""
        config_content = """
accounts:
  - name: disabled-account
    platform: bluesky
    enabled: false
    credentials:
      handle: user.bsky.social
      app-password: test
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        config = Config.from_yaml(config_file)

        assert len(config.accounts) == 1
        assert config.accounts[0].enabled is False

    def test_file_not_found(self, tmp_path):
        """Test that FileNotFoundError is raised when no config exists."""
        nonexistent = tmp_path / "nonexistent.yaml"
        with pytest.raises(FileNotFoundError):
            Config.from_yaml(nonexistent)


class TestYamlValidation:
    """Tests for YAML config validation."""

    def test_empty_config(self, tmp_path):
        """Test that empty config raises ConfigurationError."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")
        with pytest.raises(ConfigurationError, match="empty"):
            Config.from_yaml(config_file)

    def test_no_accounts(self, tmp_path):
        """Test that missing accounts raises ConfigurationError."""
        config_content = """
settings:
  log-level: INFO
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        with pytest.raises(ConfigurationError, match="[Aa]t least one account"):
            Config.from_yaml(config_file)

    def test_duplicate_account_names(self, tmp_path):
        """Test that duplicate account names raise ConfigurationError."""
        config_content = """
accounts:
  - name: my-account
    platform: bluesky
    credentials:
      handle: user1.bsky.social
      app-password: pass1

  - name: my-account
    platform: mastodon
    credentials:
      instance-url: https://mastodon.social
      access-token: token
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        with pytest.raises(ConfigurationError, match="Duplicate account name"):
            Config.from_yaml(config_file)

    def test_missing_account_name(self, tmp_path):
        """Test that missing account name raises ConfigurationError."""
        config_content = """
accounts:
  - platform: bluesky
    credentials:
      handle: user.bsky.social
      app-password: test
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        with pytest.raises(ConfigurationError, match="name is required"):
            Config.from_yaml(config_file)

    def test_unknown_platform(self, tmp_path):
        """Test that unknown platform raises ConfigurationError."""
        config_content = """
accounts:
  - name: test
    platform: twitter
    credentials:
      username: test
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        with pytest.raises(ConfigurationError, match="Unknown platform"):
            Config.from_yaml(config_file)

    def test_missing_credentials(self, tmp_path):
        """Test that missing credentials raise ConfigurationError."""
        config_content = """
accounts:
  - name: test-bluesky
    platform: bluesky
    credentials:
      handle: user.bsky.social
      # Missing app-password
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        with pytest.raises(ConfigurationError, match="Missing credentials"):
            Config.from_yaml(config_file)


class TestGetConfig:
    """Tests for get_config function."""

    def test_yaml_takes_precedence(self, sample_yaml_config, monkeypatch):
        """Test that YAML config takes precedence over env vars."""
        # Set up env vars that would normally be used
        monkeypatch.setenv("BLUESKY_HANDLE", "env.bsky.social")
        monkeypatch.setenv("BLUESKY_APP_PASSWORD", "env_pass")

        # Change to the directory with the YAML file
        original_cwd = os.getcwd()
        try:
            os.chdir(sample_yaml_config.parent)

            # Reset global config
            import ripplecast.config

            ripplecast.config._config = None

            config = get_config()

            # Should have accounts from YAML, not env vars
            assert len(config.accounts) == 2
            assert config.accounts[0].name == "test-mastodon"
        finally:
            os.chdir(original_cwd)
            ripplecast.config._config = None

    def test_error_when_no_yaml(self, tmp_path, monkeypatch):
        """Test that FileNotFoundError is raised when no YAML exists."""
        # Change to empty directory (no config.yaml file)
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            # Ensure ~/.config/ripplecast/config.yaml is not found either
            monkeypatch.setattr(Path, "home", lambda: tmp_path / "fakehome")

            # Reset global config
            import ripplecast.config

            ripplecast.config._config = None

            with pytest.raises(FileNotFoundError):
                get_config()
        finally:
            os.chdir(original_cwd)
            ripplecast.config._config = None


class TestReloadConfig:
    """Tests for reload_config function."""

    def test_reload_from_yaml(self, sample_yaml_config):
        """Test reloading config from specific YAML file."""
        config = reload_config(yaml_path=sample_yaml_config)

        assert len(config.accounts) == 2
        assert config.settings.log_level == "DEBUG"
