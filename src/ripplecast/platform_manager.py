"""Platform plugin registry and routing."""

import logging
from typing import Any

from ripplecast.config import get_config
from ripplecast.models import PlatformNotFoundError, Post
from ripplecast.platforms.base import PlatformPlugin
from ripplecast.platforms.bluesky import BlueskyPlugin
from ripplecast.platforms.mastodon import MastodonPlugin

logger = logging.getLogger(__name__)


class PlatformManager:
    """Manages platform plugins and routes requests."""

    def __init__(self) -> None:
        self._platforms: dict[str, PlatformPlugin] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize and authenticate all configured platforms."""
        if self._initialized:
            return

        config = get_config()

        # Register Mastodon
        if config.mastodon.is_configured:
            mastodon = MastodonPlugin(config.mastodon)
            self._platforms["mastodon"] = mastodon
            logger.info("Mastodon plugin registered")

        # Register Bluesky
        if config.bluesky.is_configured:
            bluesky = BlueskyPlugin(config.bluesky)
            self._platforms["bluesky"] = bluesky
            logger.info("Bluesky plugin registered")

        # Authenticate all platforms
        for name, plugin in self._platforms.items():
            try:
                success = await plugin.authenticate()
                if success:
                    logger.info(f"Successfully authenticated with {name}")
                else:
                    logger.warning(f"Failed to authenticate with {name}")
            except Exception as e:
                logger.error(f"Error authenticating with {name}: {e}")

        self._initialized = True

    def get_platform(self, name: str) -> PlatformPlugin:
        """Get a platform plugin by name."""
        if name not in self._platforms:
            raise PlatformNotFoundError(f"Platform '{name}' is not configured")
        return self._platforms[name]

    def get_all_platforms(self) -> dict[str, PlatformPlugin]:
        """Get all registered platform plugins."""
        return self._platforms.copy()

    def list_platforms(self) -> list[dict[str, Any]]:
        """List all platforms and their connection status."""
        platforms = []
        for name, plugin in self._platforms.items():
            platforms.append(
                {
                    "name": name,
                    "display_name": plugin.display_name,
                    "connected": plugin.connected,
                    "max_post_length": plugin.max_post_length,
                }
            )
        return platforms

    async def get_platform_status(self) -> list[dict[str, Any]]:
        """Get detailed status for all platforms including user info."""
        statuses = []
        for name, plugin in self._platforms.items():
            status: dict[str, Any] = {
                "name": name,
                "display_name": plugin.display_name,
                "connected": plugin.connected,
            }

            if plugin.connected:
                try:
                    user = await plugin.get_current_user()
                    status["username"] = user.get("username")
                    status["url"] = user.get("url")
                    if "instance_url" in user:
                        status["instance_url"] = user["instance_url"]
                except Exception as e:
                    status["error"] = str(e)
            else:
                status["error"] = "Not authenticated"

            statuses.append(status)

        return statuses

    async def get_posts(
        self,
        platform: str,
        limit: int = 20,
        exclude_replies: bool = True,
        exclude_reposts: bool = True,
    ) -> list[Post]:
        """Get posts from a specific platform."""
        plugin = self.get_platform(platform)
        return await plugin.get_posts(
            limit=limit,
            exclude_replies=exclude_replies,
            exclude_reposts=exclude_reposts,
        )

    async def get_all_posts(
        self,
        limit: int = 20,
        exclude_replies: bool = True,
        exclude_reposts: bool = True,
    ) -> dict[str, list[Post]]:
        """Get posts from all connected platforms."""
        result: dict[str, list[Post]] = {}

        for name, plugin in self._platforms.items():
            if plugin.connected:
                try:
                    posts = await plugin.get_posts(
                        limit=limit,
                        exclude_replies=exclude_replies,
                        exclude_reposts=exclude_reposts,
                    )
                    result[name] = posts
                except Exception as e:
                    logger.error(f"Error fetching posts from {name}: {e}")
                    result[name] = []

        return result

    async def create_post(
        self,
        platform: str,
        text: str,
        language: str | None = None,
    ) -> Post:
        """Create a post on a specific platform."""
        plugin = self.get_platform(platform)
        return await plugin.create_post(text=text, language=language)

    async def get_post_by_id(self, platform: str, post_id: str) -> Post | None:
        """Get a specific post by ID from a platform."""
        plugin = self.get_platform(platform)
        return await plugin.get_post_by_id(post_id)


# Global platform manager instance (lazy initialized)
_manager: PlatformManager | None = None


async def get_platform_manager() -> PlatformManager:
    """Get the global platform manager instance."""
    global _manager
    if _manager is None:
        _manager = PlatformManager()
        await _manager.initialize()
    return _manager
