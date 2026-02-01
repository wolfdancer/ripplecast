"""Mastodon platform plugin."""

import io
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from mastodon import Mastodon, MastodonAPIError, MastodonUnauthorizedError

from ripplecast.config import MastodonConfig

if TYPE_CHECKING:
    from ripplecast.media import DownloadedMedia
from ripplecast.models import (
    AuthenticationError,
    LinkEmbed,
    MediaAttachment,
    Post,
    PostNotFoundError,
    PostTooLongError,
    RateLimitError,
)
from ripplecast.platforms.base import PlatformPlugin

logger = logging.getLogger(__name__)


class MastodonPlugin(PlatformPlugin):
    """Mastodon platform implementation."""

    def __init__(self, config: MastodonConfig):
        self._config = config
        self._client: Mastodon | None = None
        self._user: dict[str, Any] | None = None
        self._connected = False
        self._instance_info: dict[str, Any] | None = None

    @property
    def platform_name(self) -> str:
        return "mastodon"

    @property
    def display_name(self) -> str:
        return "Mastodon"

    @property
    def max_post_length(self) -> int:
        # Default to 500, but can be overridden by instance config
        if self._instance_info:
            return self._instance_info.get("max_toot_chars", 500)
        return 500

    @property
    def connected(self) -> bool:
        return self._connected

    async def authenticate(self) -> bool:
        """Authenticate with Mastodon using the configured access token."""
        if not self._config.is_configured:
            logger.warning("Mastodon credentials not configured")
            return False

        try:
            self._client = Mastodon(
                access_token=self._config.access_token,
                api_base_url=self._config.instance_url,
            )
            # Verify credentials by fetching current user
            self._user = self._client.account_verify_credentials()
            self._instance_info = self._client.instance()
            self._connected = True
            logger.info(f"Authenticated as @{self._user['username']}@{self._config.instance_url}")
            return True
        except MastodonUnauthorizedError:
            logger.error("Mastodon authentication failed: Invalid access token")
            self._connected = False
            return False
        except Exception as e:
            logger.error(f"Mastodon authentication failed: {e}")
            self._connected = False
            return False

    async def get_current_user(self) -> dict[str, Any]:
        """Get the authenticated user's profile information."""
        if not self._connected or not self._user:
            raise AuthenticationError("Not authenticated with Mastodon")

        return {
            "id": self._user["id"],
            "username": f"@{self._user['username']}@{self._config.instance_url.replace('https://', '')}",
            "display_name": self._user.get("display_name", self._user["username"]),
            "url": self._user["url"],
            "instance_url": self._config.instance_url,
        }

    async def get_posts(
        self,
        limit: int = 20,
        since_id: str | None = None,
        max_id: str | None = None,
        exclude_replies: bool = True,
        exclude_reposts: bool = True,
    ) -> list[Post]:
        """Fetch recent posts from the authenticated user."""
        if not self._connected or not self._client or not self._user:
            raise AuthenticationError("Not authenticated with Mastodon")

        try:
            statuses = self._client.account_statuses(
                self._user["id"],
                limit=min(limit, 100),  # Mastodon max is 40 per request typically
                since_id=since_id,
                max_id=max_id,
                exclude_replies=exclude_replies,
                exclude_reblogs=exclude_reposts,
            )

            posts = []
            for status in statuses:
                post = self._status_to_post(status)
                posts.append(post)

            return posts

        except MastodonAPIError as e:
            if "rate limit" in str(e).lower():
                raise RateLimitError("mastodon")
            raise

    async def create_post(
        self,
        text: str,
        media: list[MediaAttachment] | None = None,
        reply_to_id: str | None = None,
        language: str | None = None,
        link_embed: "LinkEmbed | None" = None,
        downloaded_media: list["DownloadedMedia"] | None = None,
    ) -> Post:
        """Create a new post on Mastodon."""
        if not self._connected or not self._client:
            raise AuthenticationError("Not authenticated with Mastodon")

        # Validate content
        is_valid, error = self.validate_post_content(text)
        if not is_valid:
            raise PostTooLongError(text, self.max_post_length, "mastodon")

        try:
            # Upload media if provided
            media_ids = None
            if downloaded_media:
                media_ids = []
                for dm in downloaded_media[:4]:  # Mastodon max 4 attachments
                    try:
                        # Create a file-like object for the media data
                        media_file = io.BytesIO(dm.data)
                        media_dict = self._client.media_post(
                            media_file=media_file,
                            mime_type=dm.mime_type,
                            description=dm.alt_text,
                        )
                        media_ids.append(media_dict["id"])
                    except Exception as e:
                        logger.warning(f"Failed to upload media: {e}")

            # Note: Mastodon auto-generates link cards from URLs in text
            # No special handling needed for link_embed
            status = self._client.status_post(
                status=text,
                in_reply_to_id=reply_to_id,
                language=language,
                media_ids=media_ids if media_ids else None,
            )

            return self._status_to_post(status)

        except MastodonAPIError as e:
            if "rate limit" in str(e).lower():
                raise RateLimitError("mastodon")
            raise

    async def delete_post(self, post_id: str) -> bool:
        """Delete a post by ID."""
        if not self._connected or not self._client:
            raise AuthenticationError("Not authenticated with Mastodon")

        try:
            self._client.status_delete(post_id)
            return True
        except MastodonAPIError:
            return False

    async def get_post_by_id(self, post_id: str) -> Post | None:
        """Fetch a specific post by ID."""
        if not self._connected or not self._client:
            raise AuthenticationError("Not authenticated with Mastodon")

        try:
            status = self._client.status(post_id)
            return self._status_to_post(status)
        except MastodonAPIError:
            raise PostNotFoundError(f"Post {post_id} not found on Mastodon")

    def _status_to_post(self, status: dict[str, Any]) -> Post:
        """Convert a Mastodon status to our Post model."""
        # Handle reblog (repost)
        is_repost = status.get("reblog") is not None
        original_id = None
        if is_repost:
            original_id = status["reblog"]["id"]
            # Use the reblogged content for text
            content = status["reblog"].get("content", "")
        else:
            content = status.get("content", "")

        # Strip HTML tags (basic)
        import re

        text = re.sub(r"<[^>]+>", "", content)
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'")

        # Parse media attachments
        media_attachments = []
        for attachment in status.get("media_attachments", []):
            media_attachments.append(
                MediaAttachment(
                    url=attachment["url"],
                    media_type=attachment["type"],
                    alt_text=attachment.get("description"),
                    mime_type=attachment.get("mime_type"),
                )
            )

        # Parse link embed (card) if present
        link_embed = None
        card = status.get("card")
        if card:
            link_embed = LinkEmbed(
                url=card.get("url", ""),
                title=card.get("title"),
                description=card.get("description"),
                thumbnail_url=card.get("image"),
            )

        # Parse created_at
        created_at = status["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

        return Post(
            id=str(status["id"]),
            platform="mastodon",
            text=text.strip(),
            created_at=created_at,
            url=status["url"],
            media_attachments=media_attachments,
            link_embed=link_embed,
            reply_to_id=status.get("in_reply_to_id"),
            is_repost=is_repost,
            original_post_id=str(original_id) if original_id else None,
            language=status.get("language"),
            raw_data=status,
        )
