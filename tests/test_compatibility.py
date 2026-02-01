"""Tests for compatibility analysis."""

from datetime import datetime, timezone

import pytest

from ripplecast.compatibility import (
    CompatibilityLevel,
    analyze_cross_post_compatibility,
    generate_recommendations,
)
from ripplecast.models import LinkEmbed, MediaAttachment, Post


class TestCompatibilityAnalysis:
    """Tests for analyze_cross_post_compatibility."""

    def test_simple_text_post_full_compat(self):
        """Short text post should be fully compatible."""
        post = Post(
            id="123",
            platform="mastodon",
            text="Hello world!",
            created_at=datetime.now(timezone.utc),
            url="https://example.com/123",
        )

        report = analyze_cross_post_compatibility(post, "bluesky")

        assert report.level == CompatibilityLevel.FULL
        assert report.can_transfer_text
        assert not report.text_needs_truncation
        assert not report.has_both_media_and_embed
        assert len(report.issues) == 0

    def test_long_text_needs_truncation_for_bluesky(self):
        """Long text should require truncation for Bluesky (300 char limit)."""
        post = Post(
            id="123",
            platform="mastodon",
            text="x" * 350,
            created_at=datetime.now(timezone.utc),
            url="https://example.com/123",
        )

        report = analyze_cross_post_compatibility(post, "bluesky")

        assert report.level == CompatibilityLevel.PARTIAL
        assert report.text_needs_truncation
        assert report.suggested_text is not None
        assert len(report.suggested_text) <= 300
        assert report.suggested_text.endswith("...")

    def test_long_text_ok_for_mastodon(self):
        """350 char text should be fine for Mastodon (500 char limit)."""
        post = Post(
            id="123",
            platform="bluesky",
            text="x" * 350,
            created_at=datetime.now(timezone.utc),
            url="https://bsky.app/123",
        )

        report = analyze_cross_post_compatibility(post, "mastodon")

        assert report.level == CompatibilityLevel.FULL
        assert not report.text_needs_truncation

    def test_media_attachments_analyzed(self):
        """Media attachments should be analyzed for compatibility."""
        post = Post(
            id="123",
            platform="mastodon",
            text="Post with images",
            created_at=datetime.now(timezone.utc),
            url="https://example.com/123",
            media_attachments=[
                MediaAttachment(
                    url="https://example.com/img.jpg",
                    media_type="image",
                    mime_type="image/jpeg",
                ),
            ],
        )

        report = analyze_cross_post_compatibility(post, "bluesky")

        assert report.can_transfer_media
        assert report.media_transfer_count == 1

    def test_multiple_media_truncated(self):
        """More than 4 media should be truncated."""
        attachments = [
            MediaAttachment(
                url=f"https://example.com/img{i}.jpg",
                media_type="image",
                mime_type="image/jpeg",
            )
            for i in range(6)
        ]
        post = Post(
            id="123",
            platform="mastodon",
            text="Many images",
            created_at=datetime.now(timezone.utc),
            url="https://example.com/123",
            media_attachments=attachments,
        )

        report = analyze_cross_post_compatibility(post, "bluesky")

        assert report.can_transfer_media
        assert report.media_transfer_count == 4  # Max for Bluesky
        assert any(i.category == "media" and "4 of 6" in i.message for i in report.issues)

    def test_link_embed_analyzed(self):
        """Link embeds should be analyzed."""
        post = Post(
            id="123",
            platform="bluesky",
            text="Check this out https://example.com",
            created_at=datetime.now(timezone.utc),
            url="https://bsky.app/post/123",
            link_embed=LinkEmbed(url="https://example.com", title="Example"),
        )

        report = analyze_cross_post_compatibility(post, "mastodon")

        assert report.can_transfer_link_embed

    def test_both_media_and_embed_conflict(self):
        """Post with both media and embed should require choice for Bluesky."""
        post = Post(
            id="123",
            platform="mastodon",
            text="Post with both",
            created_at=datetime.now(timezone.utc),
            url="https://example.com/123",
            media_attachments=[
                MediaAttachment(
                    url="https://example.com/img.jpg",
                    media_type="image",
                    mime_type="image/jpeg",
                ),
            ],
            link_embed=LinkEmbed(url="https://example.com", title="Example"),
        )

        report = analyze_cross_post_compatibility(post, "bluesky")

        assert report.level == CompatibilityLevel.REQUIRES_CHOICE
        assert report.has_both_media_and_embed
        assert any(i.category == "conflict" for i in report.issues)

    def test_mastodon_url_warning_for_card(self):
        """Mastodon should warn if URL not in text for card generation."""
        post = Post(
            id="123",
            platform="bluesky",
            text="Check this article!",  # URL not in text
            created_at=datetime.now(timezone.utc),
            url="https://bsky.app/post/123",
            link_embed=LinkEmbed(url="https://different.com/article", title="Article"),
        )

        report = analyze_cross_post_compatibility(post, "mastodon")

        assert report.can_transfer_link_embed
        assert any(
            i.category == "embed" and "URL" in i.message
            for i in report.issues
        )


class TestRecommendations:
    """Tests for generate_recommendations."""

    def test_truncation_recommendation(self):
        """Should recommend truncation for long text."""
        post = Post(
            id="123",
            platform="mastodon",
            text="x" * 400,
            created_at=datetime.now(timezone.utc),
            url="https://example.com/123",
        )

        report = analyze_cross_post_compatibility(post, "bluesky")
        recommendations = generate_recommendations(report)

        assert any("shortened" in r.lower() for r in recommendations)

    def test_choice_recommendation(self):
        """Should recommend choosing between media and embed."""
        post = Post(
            id="123",
            platform="mastodon",
            text="Both",
            created_at=datetime.now(timezone.utc),
            url="https://example.com/123",
            media_attachments=[
                MediaAttachment(url="https://example.com/img.jpg", media_type="image"),
            ],
            link_embed=LinkEmbed(url="https://example.com"),
        )

        report = analyze_cross_post_compatibility(post, "bluesky")
        recommendations = generate_recommendations(report)

        assert any("transfer_media" in r or "transfer_link_embed" in r for r in recommendations)

    def test_media_count_recommendation(self):
        """Should report transferable media count."""
        post = Post(
            id="123",
            platform="mastodon",
            text="Images",
            created_at=datetime.now(timezone.utc),
            url="https://example.com/123",
            media_attachments=[
                MediaAttachment(url="https://example.com/img.jpg", media_type="image"),
                MediaAttachment(url="https://example.com/img2.jpg", media_type="image"),
            ],
        )

        report = analyze_cross_post_compatibility(post, "bluesky")
        recommendations = generate_recommendations(report)

        assert any("2 media" in r for r in recommendations)


class TestCompatibilityReport:
    """Tests for CompatibilityReport.to_dict()."""

    def test_to_dict_structure(self):
        """Verify to_dict returns expected structure."""
        post = Post(
            id="123",
            platform="mastodon",
            text="Test",
            created_at=datetime.now(timezone.utc),
            url="https://example.com/123",
        )

        report = analyze_cross_post_compatibility(post, "bluesky")
        result = report.to_dict()

        assert "source_platform" in result
        assert "target_platform" in result
        assert "level" in result
        assert "can_transfer" in result
        assert result["can_transfer"]["text"] is True
        assert "issues" in result
        assert isinstance(result["issues"], list)
