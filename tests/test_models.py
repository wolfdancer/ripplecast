"""Tests for data models."""

from datetime import datetime, timezone

import pytest

from ripplecast.models import (
    MediaAttachment,
    Post,
    PostMatch,
    PostTooLongError,
    RateLimitError,
)


class TestPost:
    """Tests for the Post model."""

    def test_post_creation(self):
        """Test creating a basic post."""
        post = Post(
            id="123",
            platform="mastodon",
            text="Hello world!",
            created_at=datetime(2025, 1, 25, 10, 0, 0, tzinfo=timezone.utc),
            url="https://example.com/123",
        )

        assert post.id == "123"
        assert post.platform == "mastodon"
        assert post.text == "Hello world!"
        assert post.url == "https://example.com/123"
        assert post.media_attachments == []
        assert post.is_repost is False

    def test_post_to_dict(self):
        """Test converting post to dictionary."""
        post = Post(
            id="123",
            platform="bluesky",
            text="Test post",
            created_at=datetime(2025, 1, 25, 10, 0, 0, tzinfo=timezone.utc),
            url="https://bsky.app/post/123",
        )

        result = post.to_dict()

        assert result["id"] == "123"
        assert result["platform"] == "bluesky"
        assert result["text"] == "Test post"
        assert result["has_media"] is False
        assert result["is_reply"] is False
        assert result["is_repost"] is False

    def test_post_with_media(self):
        """Test post with media attachments."""
        media = MediaAttachment(
            url="https://example.com/image.png",
            media_type="image",
            alt_text="A test image",
        )
        post = Post(
            id="123",
            platform="mastodon",
            text="Check this out!",
            created_at=datetime.now(timezone.utc),
            url="https://example.com/123",
            media_attachments=[media],
        )

        assert len(post.media_attachments) == 1
        assert post.to_dict()["has_media"] is True
        assert post.to_dict()["media_count"] == 1


class TestPostMatch:
    """Tests for the PostMatch model."""

    def test_post_match_creation(self):
        """Test creating a post match."""
        match = PostMatch(
            post_a_id="123",
            post_b_id="456",
            confidence=0.95,
            reason="identical text",
        )

        assert match.post_a_id == "123"
        assert match.post_b_id == "456"
        assert match.confidence == 0.95
        assert match.reason == "identical text"


class TestExceptions:
    """Tests for custom exceptions."""

    def test_post_too_long_error(self):
        """Test PostTooLongError."""
        text = "x" * 350
        error = PostTooLongError(text, 300, "bluesky")

        assert error.text == text
        assert error.limit == 300
        assert error.platform == "bluesky"
        assert error.length == 350
        assert "350 chars" in str(error)
        assert "bluesky" in str(error)
        assert "max 300" in str(error)

    def test_rate_limit_error_without_retry(self):
        """Test RateLimitError without retry_after."""
        error = RateLimitError("mastodon")

        assert error.platform == "mastodon"
        assert error.retry_after is None
        assert "Rate limited by mastodon" in str(error)

    def test_rate_limit_error_with_retry(self):
        """Test RateLimitError with retry_after."""
        error = RateLimitError("bluesky", retry_after=60)

        assert error.platform == "bluesky"
        assert error.retry_after == 60
        assert "retry after 60 seconds" in str(error)
