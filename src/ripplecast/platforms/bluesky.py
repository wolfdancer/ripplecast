"""Bluesky platform plugin."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from atproto import Client, models
from atproto.exceptions import AtProtocolError, UnauthorizedError

from ripplecast.config import BlueskyConfig

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


class BlueskyPlugin(PlatformPlugin):
    """Bluesky platform implementation."""

    @staticmethod
    def _expand_facets_in_text(text: str, facets: list[Any] | None) -> str:
        """Expand truncated URLs in text using facet metadata.

        Bluesky stores full URLs in facets while displaying truncated versions.
        This method reconstructs the text with full URLs for cross-posting.

        Args:
            text: The original post text (may contain truncated URLs)
            facets: List of facet objects with byte indices and features

        Returns:
            Text with truncated URLs replaced by their full versions
        """
        if not facets:
            return text

        # Convert text to bytes for proper offset handling
        text_bytes = text.encode("utf-8")

        # Collect all link facets with their byte ranges and URIs
        replacements = []
        for facet in facets:
            if not hasattr(facet, "index") or not hasattr(facet, "features"):
                continue

            byte_start = facet.index.byte_start
            byte_end = facet.index.byte_end

            # Find link features in this facet
            for feature in facet.features:
                # Check for link type facet
                if hasattr(feature, "uri"):
                    uri = feature.uri
                    replacements.append((byte_start, byte_end, uri))
                    break  # Only one replacement per facet

        if not replacements:
            return text

        # Sort replacements by byte_start in reverse order to avoid offset issues
        replacements.sort(key=lambda x: x[0], reverse=True)

        # Apply replacements from end to start
        result_bytes = text_bytes
        for byte_start, byte_end, uri in replacements:
            result_bytes = result_bytes[:byte_start] + uri.encode("utf-8") + result_bytes[byte_end:]

        return result_bytes.decode("utf-8")

    def __init__(self, config: BlueskyConfig):
        self._config = config
        self._client: Client | None = None
        self._connected = False

    @property
    def platform_name(self) -> str:
        return "bluesky"

    @property
    def display_name(self) -> str:
        return "Bluesky"

    @property
    def max_post_length(self) -> int:
        return 300

    @property
    def connected(self) -> bool:
        return self._connected

    async def authenticate(self) -> bool:
        """Authenticate with Bluesky using the configured app password."""
        if not self._config.is_configured:
            logger.warning("Bluesky credentials not configured")
            return False

        try:
            self._client = Client()
            self._client.login(self._config.handle, self._config.app_password)
            self._connected = True
            logger.info(f"Authenticated as {self._config.handle}")
            return True
        except UnauthorizedError:
            logger.error("Bluesky authentication failed: Invalid credentials")
            self._connected = False
            return False
        except Exception as e:
            logger.error(f"Bluesky authentication failed: {e}")
            self._connected = False
            return False

    async def get_current_user(self) -> dict[str, Any]:
        """Get the authenticated user's profile information."""
        if not self._connected or not self._client:
            raise AuthenticationError("Not authenticated with Bluesky")

        profile = self._client.get_profile(actor=self._client.me.did)

        return {
            "id": self._client.me.did,
            "username": profile.handle,
            "display_name": profile.display_name or profile.handle,
            "url": f"https://bsky.app/profile/{profile.handle}",
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
        if not self._connected or not self._client:
            raise AuthenticationError("Not authenticated with Bluesky")

        try:
            response = self._client.get_author_feed(
                actor=self._client.me.did,
                limit=min(limit, 100),
                cursor=max_id,
            )

            posts = []
            for feed_item in response.feed:
                post = feed_item.post
                reason = feed_item.reason

                # Check if this is a repost
                is_repost = reason is not None and hasattr(reason, "py_type")

                # Skip reposts if requested
                if exclude_reposts and is_repost:
                    continue

                # Skip replies if requested
                if exclude_replies and post.record.reply is not None:
                    continue

                # Skip if we've passed the since_id
                if since_id and post.uri == since_id:
                    break

                converted_post = self._feed_post_to_post(post, is_repost)
                posts.append(converted_post)

            return posts

        except AtProtocolError as e:
            if "rate" in str(e).lower():
                raise RateLimitError("bluesky")
            raise

    async def create_post(
        self,
        text: str,
        media: list[MediaAttachment] | None = None,
        reply_to_id: str | None = None,
        language: str | None = None,
        link_embed: LinkEmbed | None = None,
        downloaded_media: list["DownloadedMedia"] | None = None,
    ) -> Post:
        """Create a new post on Bluesky."""
        if not self._connected or not self._client:
            raise AuthenticationError("Not authenticated with Bluesky")

        # Validate content
        is_valid, error = self.validate_post_content(text)
        if not is_valid:
            raise PostTooLongError(text, self.max_post_length, "bluesky")

        try:
            embed = None

            # Handle image embeds (takes priority over link embeds)
            if downloaded_media:
                images = []
                for dm in downloaded_media[:4]:  # Bluesky max 4 images
                    if dm.is_image:
                        blob_response = self._client.upload_blob(dm.data)
                        images.append(
                            models.AppBskyEmbedImages.Image(
                                image=blob_response.blob,
                                alt=dm.alt_text or "",
                            )
                        )
                if images:
                    embed = models.AppBskyEmbedImages.Main(images=images)

            # Handle external link embed (only if no media embed)
            elif link_embed:
                external = models.AppBskyEmbedExternal.External(
                    uri=link_embed.url,
                    title=link_embed.title or "",
                    description=link_embed.description or "",
                )
                # Add thumbnail if available
                if link_embed.thumbnail_data:
                    thumb_response = self._client.upload_blob(link_embed.thumbnail_data)
                    external.thumb = thumb_response.blob
                embed = models.AppBskyEmbedExternal.Main(external=external)

            record = models.AppBskyFeedPost.Record(
                created_at=self._client.get_current_time_iso(),
                text=text,
                embed=embed,
                via="ripplecast",
            )
            response = self._client.app.bsky.feed.post.create(
                self._client.me.did, record
            )

            # Return the created post
            return Post(
                id=response.uri,
                platform="bluesky",
                text=text,
                created_at=datetime.now(),
                url=self._uri_to_url(response.uri),
                raw_data={"uri": response.uri, "cid": response.cid, "via": "ripplecast"},
            )

        except AtProtocolError as e:
            if "rate" in str(e).lower():
                raise RateLimitError("bluesky")
            raise

    async def delete_post(self, post_id: str) -> bool:
        """Delete a post by ID (URI)."""
        if not self._connected or not self._client:
            raise AuthenticationError("Not authenticated with Bluesky")

        try:
            self._client.delete_post(post_id)
            return True
        except AtProtocolError:
            return False

    async def get_post_by_id(self, post_id: str) -> Post | None:
        """Fetch a specific post by ID (URI)."""
        if not self._connected or not self._client:
            raise AuthenticationError("Not authenticated with Bluesky")

        try:
            # Parse the URI to get repo and rkey
            # URI format: at://did:plc:xxx/app.bsky.feed.post/xxx
            parts = post_id.replace("at://", "").split("/")
            if len(parts) < 3:
                raise PostNotFoundError(f"Invalid post URI: {post_id}")

            repo = parts[0]
            rkey = parts[2]

            response = self._client.get_post(rkey, repo)

            # Parse media attachments and link embeds
            media_attachments = []
            link_embed = None
            if hasattr(response.value, "embed") and response.value.embed:
                embed = response.value.embed
                if hasattr(embed, "images"):
                    for img in embed.images:
                        media_attachments.append(
                            MediaAttachment(
                                url=img.fullsize if hasattr(img, "fullsize") else "",
                                media_type="image",
                                alt_text=img.alt if hasattr(img, "alt") else None,
                            )
                        )
                if hasattr(embed, "external"):
                    ext = embed.external
                    link_embed = LinkEmbed(
                        url=ext.uri if hasattr(ext, "uri") else "",
                        title=ext.title if hasattr(ext, "title") else None,
                        description=ext.description if hasattr(ext, "description") else None,
                        thumbnail_url=None,
                    )

            # Expand facets to get full URLs in text (Bluesky truncates display URLs)
            facets = getattr(response.value, "facets", None)
            expanded_text = self._expand_facets_in_text(response.value.text, facets)

            return Post(
                id=response.uri,
                platform="bluesky",
                text=expanded_text,
                created_at=datetime.fromisoformat(response.value.created_at.replace("Z", "+00:00")),
                url=self._uri_to_url(response.uri),
                media_attachments=media_attachments,
                link_embed=link_embed,
                raw_data={"uri": response.uri, "cid": response.cid, "via": getattr(response.value, "via", None)},
            )

        except AtProtocolError:
            raise PostNotFoundError(f"Post {post_id} not found on Bluesky")

    def _feed_post_to_post(self, post: Any, is_repost: bool = False) -> Post:
        """Convert a Bluesky feed post to our Post model."""
        # Parse media attachments and link embeds if present
        media_attachments = []
        link_embed = None
        if hasattr(post.record, "embed") and post.record.embed:
            embed = post.record.embed
            # Check for image embeds
            if hasattr(embed, "images"):
                for img in embed.images:
                    media_attachments.append(
                        MediaAttachment(
                            url=img.fullsize if hasattr(img, "fullsize") else "",
                            media_type="image",
                            alt_text=img.alt if hasattr(img, "alt") else None,
                        )
                    )
            # Check for external link embed (app.bsky.embed.external)
            if hasattr(embed, "external"):
                ext = embed.external
                link_embed = LinkEmbed(
                    url=ext.uri if hasattr(ext, "uri") else "",
                    title=ext.title if hasattr(ext, "title") else None,
                    description=ext.description if hasattr(ext, "description") else None,
                    thumbnail_url=None,  # Bluesky stores as blob, not URL
                )

        # Parse created_at
        created_at = post.record.created_at
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

        # Check if reply
        reply_to_id = None
        if hasattr(post.record, "reply") and post.record.reply:
            reply_to_id = post.record.reply.parent.uri

        # Expand facets to get full URLs in text (Bluesky truncates display URLs)
        facets = getattr(post.record, "facets", None)
        expanded_text = self._expand_facets_in_text(post.record.text, facets)

        return Post(
            id=post.uri,
            platform="bluesky",
            text=expanded_text,
            created_at=created_at,
            url=self._uri_to_url(post.uri),
            media_attachments=media_attachments,
            link_embed=link_embed,
            reply_to_id=reply_to_id,
            is_repost=is_repost,
            language=(
                post.record.langs[0]
                if hasattr(post.record, "langs") and post.record.langs
                else None
            ),
            raw_data={"uri": post.uri, "cid": post.cid, "via": getattr(post.record, "via", None)},
        )

    def is_posted_via_ripplecast(self, post: Post) -> bool:
        """Check for a 'via' field in raw_data populated when ripplecast creates posts."""
        via = post.raw_data.get("via", "")
        return isinstance(via, str) and "ripplecast" in via.lower()

    def _uri_to_url(self, uri: str) -> str:
        """Convert an AT Protocol URI to a bsky.app URL."""
        # URI format: at://did:plc:xxx/app.bsky.feed.post/rkey
        # URL format: https://bsky.app/profile/handle/post/rkey
        try:
            parts = uri.replace("at://", "").split("/")
            did = parts[0]
            rkey = parts[2] if len(parts) > 2 else ""

            # Get handle from DID (we might need to resolve this)
            handle = self._config.handle

            return f"https://bsky.app/profile/{handle}/post/{rkey}"
        except Exception:
            return uri
