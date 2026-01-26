"""Tests for post matching service."""

import pytest

from ripplecast.matching import build_sync_summary, find_unmatched_posts
from ripplecast.models import PostMatch


class TestFindUnmatchedPosts:
    """Tests for find_unmatched_posts function."""

    def test_finds_unmatched_posts_platform_a(self, sample_mastodon_posts):
        """Test finding unmatched posts from platform A."""
        matches = [
            PostMatch(
                post_a_id="111",
                post_b_id="aaa",
                confidence=1.0,
                reason="identical",
            )
        ]

        unmatched = find_unmatched_posts(sample_mastodon_posts, matches, "a")

        assert len(unmatched) == 2
        assert unmatched[0].id == "222"
        assert unmatched[1].id == "333"

    def test_finds_unmatched_posts_platform_b(self, sample_bluesky_posts):
        """Test finding unmatched posts from platform B."""
        matches = [
            PostMatch(
                post_a_id="111",
                post_b_id="at://did:plc:test/app.bsky.feed.post/aaa",
                confidence=1.0,
                reason="identical",
            )
        ]

        unmatched = find_unmatched_posts(sample_bluesky_posts, matches, "b")

        assert len(unmatched) == 1
        assert unmatched[0].id == "at://did:plc:test/app.bsky.feed.post/bbb"

    def test_no_matches_returns_all(self, sample_mastodon_posts):
        """Test that no matches returns all posts."""
        matches = []

        unmatched = find_unmatched_posts(sample_mastodon_posts, matches, "a")

        assert len(unmatched) == len(sample_mastodon_posts)

    def test_all_matched_returns_empty(self, sample_mastodon_posts):
        """Test that all matched returns empty list."""
        matches = [
            PostMatch(post_a_id="111", post_b_id="x", confidence=1.0, reason=""),
            PostMatch(post_a_id="222", post_b_id="y", confidence=1.0, reason=""),
            PostMatch(post_a_id="333", post_b_id="z", confidence=1.0, reason=""),
        ]

        unmatched = find_unmatched_posts(sample_mastodon_posts, matches, "a")

        assert len(unmatched) == 0


class TestBuildSyncSummary:
    """Tests for build_sync_summary function."""

    def test_builds_correct_summary(self, sample_mastodon_posts, sample_bluesky_posts):
        """Test building a sync summary."""
        matches = [
            PostMatch(
                post_a_id="111",
                post_b_id="at://did:plc:test/app.bsky.feed.post/aaa",
                confidence=1.0,
                reason="identical text",
            )
        ]

        summary = build_sync_summary(sample_mastodon_posts, sample_bluesky_posts, matches)

        assert len(summary["mastodon_only"]) == 2
        assert len(summary["bluesky_only"]) == 1
        assert len(summary["synced"]) == 1

        assert summary["summary"]["mastodon_only_count"] == 2
        assert summary["summary"]["bluesky_only_count"] == 1
        assert summary["summary"]["synced_count"] == 1
        assert summary["summary"]["total_mastodon"] == 3
        assert summary["summary"]["total_bluesky"] == 2

    def test_empty_posts(self):
        """Test with empty post lists."""
        summary = build_sync_summary([], [], [])

        assert summary["mastodon_only"] == []
        assert summary["bluesky_only"] == []
        assert summary["synced"] == []
        assert summary["summary"]["mastodon_only_count"] == 0
        assert summary["summary"]["bluesky_only_count"] == 0
        assert summary["summary"]["synced_count"] == 0
