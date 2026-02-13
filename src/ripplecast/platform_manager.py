"""Platform plugin registry and routing."""

import logging
from typing import Any

from ripplecast.config import get_config
from ripplecast.models import AccountNotFoundError, Post
from ripplecast.platforms.base import PlatformPlugin
from ripplecast.platforms.bluesky import BlueskyPlugin
from ripplecast.platforms.mastodon import MastodonPlugin

logger = logging.getLogger(__name__)


class PlatformManager:
    """Manages platform plugins and routes requests.

    Accounts are keyed by their unique name (e.g., "personal-bluesky", "work-mastodon").
    """

    def __init__(self) -> None:
        self._accounts: dict[str, PlatformPlugin] = {}
        self._account_platforms: dict[str, str] = {}  # account name -> platform type
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize and authenticate all configured accounts."""
        if self._initialized:
            return

        config = get_config()

        # Register all enabled accounts
        for account in config.accounts:
            if not account.enabled:
                logger.info(f"Skipping disabled account: {account.name}")
                continue

            try:
                plugin = self._create_plugin(account.platform, account.get_platform_config())
                self._accounts[account.name] = plugin
                self._account_platforms[account.name] = account.platform
                logger.info(f"Account '{account.name}' ({account.platform}) registered")
            except ValueError as e:
                logger.error(f"Failed to create plugin for account '{account.name}': {e}")
                continue

        # Authenticate all accounts
        for name, plugin in self._accounts.items():
            try:
                success = await plugin.authenticate()
                if success:
                    logger.info(f"Successfully authenticated account '{name}'")
                else:
                    logger.warning(f"Failed to authenticate account '{name}'")
            except Exception as e:
                logger.error(f"Error authenticating account '{name}': {e}")

        self._initialized = True

    def _create_plugin(self, platform: str, config: Any) -> PlatformPlugin:
        """Factory method to create a plugin instance."""
        if platform == "mastodon":
            return MastodonPlugin(config)
        elif platform == "bluesky":
            return BlueskyPlugin(config)
        else:
            raise ValueError(f"Unknown platform: {platform}")

    def get_account(self, name: str) -> PlatformPlugin:
        """Get a plugin by account name.

        Args:
            name: Account name (e.g., "personal-bluesky", "work-mastodon")

        Returns:
            The platform plugin for this account

        Raises:
            AccountNotFoundError: If account is not configured
        """
        if name not in self._accounts:
            raise AccountNotFoundError(f"Account '{name}' is not configured")
        return self._accounts[name]

    def get_account_platform(self, name: str) -> str:
        """Get the platform type for an account.

        Args:
            name: Account name

        Returns:
            Platform type ("mastodon" or "bluesky")
        """
        if name not in self._account_platforms:
            raise AccountNotFoundError(f"Account '{name}' is not configured")
        return self._account_platforms[name]

    # Deprecated alias for backward compatibility
    def get_platform(self, name: str) -> PlatformPlugin:
        """DEPRECATED: Use get_account() instead."""
        return self.get_account(name)

    def get_all_accounts(self) -> dict[str, PlatformPlugin]:
        """Get all registered account plugins."""
        return self._accounts.copy()

    # Deprecated alias for backward compatibility
    def get_all_platforms(self) -> dict[str, PlatformPlugin]:
        """DEPRECATED: Use get_all_accounts() instead."""
        return self.get_all_accounts()

    def list_accounts(self) -> list[dict[str, Any]]:
        """List all accounts and their connection status."""
        accounts = []
        for name, plugin in self._accounts.items():
            accounts.append(
                {
                    "name": name,
                    "platform": self._account_platforms[name],
                    "display_name": plugin.display_name,
                    "connected": plugin.connected,
                    "max_post_length": plugin.max_post_length,
                }
            )
        return accounts

    # Deprecated alias for backward compatibility
    def list_platforms(self) -> list[dict[str, Any]]:
        """DEPRECATED: Use list_accounts() instead."""
        return self.list_accounts()

    async def get_account_status(self) -> list[dict[str, Any]]:
        """Get detailed status for all accounts including user info."""
        statuses = []
        for name, plugin in self._accounts.items():
            status: dict[str, Any] = {
                "name": name,
                "platform": self._account_platforms[name],
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

    # Deprecated alias for backward compatibility
    async def get_platform_status(self) -> list[dict[str, Any]]:
        """DEPRECATED: Use get_account_status() instead."""
        return await self.get_account_status()

    async def get_posts(
        self,
        account: str,
        limit: int = 20,
        exclude_replies: bool = True,
        exclude_reposts: bool = True,
    ) -> list[Post]:
        """Get posts from a specific account.

        Args:
            account: Account name (e.g., "personal-bluesky")
            limit: Maximum number of posts to fetch
            exclude_replies: Exclude reply posts
            exclude_reposts: Exclude reposted content

        Returns:
            List of posts from the account
        """
        plugin = self.get_account(account)
        posts = await plugin.get_posts(
            limit=limit,
            exclude_replies=exclude_replies,
            exclude_reposts=exclude_reposts,
        )
        # Annotate posts with account name
        for post in posts:
            post.account = account
        return posts

    async def get_all_posts(
        self,
        limit: int = 20,
        exclude_replies: bool = True,
        exclude_reposts: bool = True,
    ) -> dict[str, list[Post]]:
        """Get posts from all connected accounts."""
        result: dict[str, list[Post]] = {}

        for name, plugin in self._accounts.items():
            if plugin.connected:
                try:
                    posts = await plugin.get_posts(
                        limit=limit,
                        exclude_replies=exclude_replies,
                        exclude_reposts=exclude_reposts,
                    )
                    # Annotate posts with account name
                    for post in posts:
                        post.account = name
                    result[name] = posts
                except Exception as e:
                    logger.error(f"Error fetching posts from account '{name}': {e}")
                    result[name] = []

        return result

    async def create_post(
        self,
        account: str,
        text: str,
        language: str | None = None,
    ) -> Post:
        """Create a post on a specific account.

        Args:
            account: Account name (e.g., "work-mastodon")
            text: Post text content
            language: Optional language code

        Returns:
            The created post
        """
        plugin = self.get_account(account)
        post = await plugin.create_post(text=text, language=language)
        post.account = account
        return post

    async def get_post_by_id(self, account: str, post_id: str) -> Post | None:
        """Get a specific post by ID from an account.

        Args:
            account: Account name
            post_id: Post ID to fetch

        Returns:
            The post if found, None otherwise
        """
        plugin = self.get_account(account)
        post = await plugin.get_post_by_id(post_id)
        if post:
            post.account = account
        return post


# Global platform manager instance (lazy initialized)
_manager: PlatformManager | None = None


async def get_platform_manager() -> PlatformManager:
    """Get the global platform manager instance."""
    global _manager
    if _manager is None:
        manager = PlatformManager()
        await manager.initialize()
        _manager = manager
    return _manager
