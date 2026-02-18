"""Abstract base class for platform plugins."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ripplecast.models import LinkEmbed, MediaAttachment, Post

if TYPE_CHECKING:
    from ripplecast.media import DownloadedMedia


class PlatformPlugin(ABC):
    """Base class for social media platform plugins."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Unique identifier for this platform (e.g., 'mastodon', 'bluesky')."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name (e.g., 'Mastodon', 'Bluesky')."""
        pass

    @property
    @abstractmethod
    def max_post_length(self) -> int:
        """Maximum characters allowed in a post."""
        pass

    @property
    @abstractmethod
    def connected(self) -> bool:
        """Whether the plugin is currently authenticated."""
        pass

    @abstractmethod
    async def authenticate(self) -> bool:
        """
        Authenticate with the platform using configured credentials.
        Returns True if successful, False otherwise.
        """
        pass

    @abstractmethod
    async def get_current_user(self) -> dict:
        """
        Get the authenticated user's profile information.
        Returns dict with at least: id, username, display_name, url
        """
        pass

    @abstractmethod
    async def get_posts(
        self,
        limit: int = 20,
        since_id: str | None = None,
        max_id: str | None = None,
        exclude_replies: bool = True,
        exclude_reposts: bool = True,
    ) -> list[Post]:
        """
        Fetch recent posts from the authenticated user's timeline.

        Args:
            limit: Maximum number of posts to return
            since_id: Only return posts newer than this ID
            max_id: Only return posts older than this ID
            exclude_replies: Filter out reply posts
            exclude_reposts: Filter out reposts/boosts

        Returns:
            List of Post objects, newest first
        """
        pass

    @abstractmethod
    async def create_post(
        self,
        text: str,
        media: list[MediaAttachment] | None = None,
        reply_to_id: str | None = None,
        language: str | None = None,
        link_embed: LinkEmbed | None = None,
        downloaded_media: list["DownloadedMedia"] | None = None,
    ) -> Post:
        """
        Create a new post on this platform.

        Args:
            text: The post content
            media: Optional media attachment metadata (for reference)
            reply_to_id: ID of post to reply to (if reply)
            language: ISO language code
            link_embed: Optional link embed to attach
            downloaded_media: Optional pre-downloaded media to upload

        Returns:
            The created Post object

        Raises:
            PostTooLongError: If text exceeds max_post_length
            MediaUploadError: If media upload fails
            AuthenticationError: If not authenticated
        """
        pass

    @abstractmethod
    async def delete_post(self, post_id: str) -> bool:
        """
        Delete a post by ID.
        Returns True if successful.
        """
        pass

    @abstractmethod
    async def get_post_by_id(self, post_id: str) -> Post | None:
        """
        Fetch a specific post by its ID.
        Returns None if not found.
        """
        pass

    def validate_post_content(self, text: str) -> tuple[bool, str | None]:
        """
        Validate post content before creating.
        Returns (is_valid, error_message).
        Default implementation checks length.
        """
        if len(text) > self.max_post_length:
            return False, f"Post exceeds {self.max_post_length} characters (got {len(text)})"
        return True, None

    @abstractmethod
    def is_posted_via_ripplecast(self, post: Post) -> bool:
        """
        Check if a post's metadata indicates it was created via ripplecast.
        Return False if the platform has no attribution mechanism.
        """
        pass
