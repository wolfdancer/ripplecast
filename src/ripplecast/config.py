"""Configuration management for Ripplecast."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SUPPORTED_PLATFORMS = {"mastodon", "bluesky"}


@dataclass
class MastodonConfig:
    """Mastodon platform configuration."""

    instance_url: str
    access_token: str

    @property
    def is_configured(self) -> bool:
        """Check if all required fields are set."""
        return bool(self.instance_url and self.access_token)


@dataclass
class BlueskyConfig:
    """Bluesky platform configuration."""

    handle: str
    app_password: str

    @property
    def is_configured(self) -> bool:
        """Check if all required fields are set."""
        return bool(self.handle and self.app_password)


@dataclass
class AccountConfig:
    """Configuration for a single account."""

    name: str  # Unique identifier (e.g., "personal-bluesky")
    platform: str  # "bluesky" or "mastodon"
    credentials: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def get_platform_config(self) -> MastodonConfig | BlueskyConfig:
        """Convert credentials to platform-specific config object."""
        if self.platform == "mastodon":
            return MastodonConfig(
                instance_url=self.credentials.get("instance-url", ""),
                access_token=self.credentials.get("access-token", ""),
            )
        elif self.platform == "bluesky":
            return BlueskyConfig(
                handle=self.credentials.get("handle", ""),
                app_password=self.credentials.get("app-password", ""),
            )
        else:
            raise ValueError(f"Unknown platform: {self.platform}")


@dataclass
class Settings:
    """Global application settings."""

    log_level: str = "INFO"


class ConfigurationError(Exception):
    """Configuration file is invalid."""

    pass


@dataclass
class Config:
    """Main configuration container."""

    accounts: list[AccountConfig] = field(default_factory=list)
    settings: Settings = field(default_factory=Settings)

    # Legacy single-account fields (for backward compatibility)
    mastodon: MastodonConfig | None = None
    bluesky: BlueskyConfig | None = None
    log_level: str = "INFO"

    @classmethod
    def from_yaml(cls, yaml_path: Path | None = None) -> "Config":
        """Load configuration from YAML file.

        Search order:
        1. Explicit path if provided
        2. ./config.yaml (project root)
        3. ~/.config/ripplecast/config.yaml
        """
        search_paths = []
        if yaml_path:
            search_paths.append(yaml_path)
        else:
            search_paths.append(Path("config.yaml"))
            search_paths.append(Path.home() / ".config" / "ripplecast" / "config.yaml")

        config_path = None
        for path in search_paths:
            if path.exists():
                config_path = path
                break

        if config_path is None:
            raise FileNotFoundError("No config.yaml file found")

        with open(config_path) as f:
            data = yaml.safe_load(f)

        if data is None:
            raise ConfigurationError("Config file is empty")

        # Parse settings
        settings_data = data.get("settings", {})
        settings = Settings(log_level=settings_data.get("log-level", "INFO"))

        # Parse accounts
        accounts_data = data.get("accounts", [])
        if not accounts_data:
            raise ConfigurationError("At least one account must be defined")

        accounts = []
        seen_names: set[str] = set()
        for acc in accounts_data:
            name = acc.get("name")
            if not name:
                raise ConfigurationError("Account name is required")
            if name in seen_names:
                raise ConfigurationError(f"Duplicate account name: {name}")
            seen_names.add(name)

            platform = acc.get("platform")
            if platform not in SUPPORTED_PLATFORMS:
                raise ConfigurationError(
                    f"Unknown platform '{platform}' for account '{name}'. "
                    f"Supported: {', '.join(SUPPORTED_PLATFORMS)}"
                )

            credentials = acc.get("credentials", {})
            enabled = acc.get("enabled", True)

            account = AccountConfig(
                name=name,
                platform=platform,
                credentials=credentials,
                enabled=enabled,
            )

            # Validate credentials
            try:
                platform_config = account.get_platform_config()
                if not platform_config.is_configured:
                    raise ConfigurationError(f"Missing credentials for account '{name}'")
            except ValueError as e:
                raise ConfigurationError(str(e)) from e

            accounts.append(account)

        return cls(
            accounts=accounts,
            settings=settings,
            log_level=settings.log_level,
        )



# Global config instance (lazy loaded)
_config: Config | None = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config.from_yaml()
    return _config


def reload_config(yaml_path: Path | None = None) -> Config:
    """Reload configuration.

    Args:
        yaml_path: Path to YAML config file (optional)
    """
    global _config
    _config = Config.from_yaml(yaml_path)
    return _config
