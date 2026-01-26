"""Configuration management for Ripplecast."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


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
class Config:
    """Main configuration container."""

    mastodon: MastodonConfig
    bluesky: BlueskyConfig
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env_path: Path | None = None) -> "Config":
        """Load configuration from environment variables."""
        if env_path:
            load_dotenv(env_path)
        else:
            load_dotenv()

        return cls(
            mastodon=MastodonConfig(
                instance_url=os.getenv("MASTODON_INSTANCE_URL", ""),
                access_token=os.getenv("MASTODON_ACCESS_TOKEN", ""),
            ),
            bluesky=BlueskyConfig(
                handle=os.getenv("BLUESKY_HANDLE", ""),
                app_password=os.getenv("BLUESKY_APP_PASSWORD", ""),
            ),
            log_level=os.getenv("RIPPLECAST_LOG_LEVEL", "INFO"),
        )


# Global config instance (lazy loaded)
_config: Config | None = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def reload_config(env_path: Path | None = None) -> Config:
    """Reload configuration from environment."""
    global _config
    _config = Config.from_env(env_path)
    return _config
