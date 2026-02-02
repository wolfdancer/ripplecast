"""Shared data models for Ripplecast."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MediaAttachment:
    """Represents a media attachment on a post."""

    url: str
    media_type: str  # "image", "video", "audio", "gif"
    alt_text: str | None = None
    mime_type: str | None = None


@dataclass
class LinkEmbed:
    """Represents a link preview/card embedded in a post."""

    url: str
    title: str | None = None
    description: str | None = None
    thumbnail_url: str | None = None
    thumbnail_data: bytes | None = field(default=None, repr=False)


@dataclass
class Post:
    """Normalized representation of a social media post across platforms."""

    id: str
    platform: str  # "mastodon" or "bluesky"
    text: str
    created_at: datetime
    url: str

    # Account identifier (e.g., "personal-bluesky", "work-mastodon")
    account: str | None = None

    # Optional fields
    media_attachments: list[MediaAttachment] = field(default_factory=list)
    link_embed: LinkEmbed | None = None
    reply_to_id: str | None = None
    is_repost: bool = False
    original_post_id: str | None = None
    language: str | None = None

    # Platform-specific raw data
    raw_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        result = {
            "id": self.id,
            "platform": self.platform,
            "account": self.account,
            "text": self.text,
            "created_at": self.created_at.isoformat(),
            "url": self.url,
            "has_media": len(self.media_attachments) > 0,
            "media_count": len(self.media_attachments),
            "has_link_embed": self.link_embed is not None,
            "is_reply": self.reply_to_id is not None,
            "is_repost": self.is_repost,
            "language": self.language,
        }
        if self.link_embed:
            result["link_embed"] = {
                "url": self.link_embed.url,
                "title": self.link_embed.title,
                "description": self.link_embed.description,
                "has_thumbnail": self.link_embed.thumbnail_url is not None,
            }
        return result


@dataclass
class SimilarPost:
    """A post that potentially matches another post."""

    post: Post
    similarity_score: float  # 0.0 to 1.0
    match_reason: str  # "exact", "fuzzy", "partial"


@dataclass
class PostComparison:
    """Result of comparing posts across platforms."""

    post: Post
    exists_on: list[str]
    missing_from: list[str]
    similar_posts: list[SimilarPost] = field(default_factory=list)


@dataclass
class PostMatch:
    """Represents a match between two posts on different platforms."""

    post_a_id: str
    post_b_id: str
    confidence: float
    reason: str


# Custom exceptions


class RipplecastError(Exception):
    """Base exception for Ripplecast."""

    pass


class AuthenticationError(RipplecastError):
    """Failed to authenticate with platform."""

    pass


class PlatformNotFoundError(RipplecastError):
    """Referenced platform is not configured."""

    pass


class AccountNotFoundError(RipplecastError):
    """Referenced account is not configured."""

    pass


class PostNotFoundError(RipplecastError):
    """Post ID not found on platform."""

    pass


class PostTooLongError(RipplecastError):
    """Post exceeds target platform character limit."""

    def __init__(self, text: str, limit: int, platform: str):
        self.text = text
        self.limit = limit
        self.platform = platform
        self.length = len(text)
        super().__init__(f"Post is {self.length} chars but {platform} allows max {limit}")


class RateLimitError(RipplecastError):
    """Hit API rate limit."""

    def __init__(self, platform: str, retry_after: int | None = None):
        self.platform = platform
        self.retry_after = retry_after
        msg = f"Rate limited by {platform}"
        if retry_after:
            msg += f", retry after {retry_after} seconds"
        super().__init__(msg)


class MediaNotSupportedError(RipplecastError):
    """Media type not supported for cross-posting."""

    pass
