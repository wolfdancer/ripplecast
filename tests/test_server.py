"""Tests for the MCP server tools."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ripplecast.models import Post, PostMatch


class TestServerTools:
    """Tests for MCP server tool functions."""

    @pytest.fixture
    def mock_platform_manager(self):
        """Create a mock platform manager that works with async context."""

        async def make_manager():
            manager = MagicMock()
            return manager

        return make_manager

    @pytest.mark.asyncio
    async def test_list_accounts(self):
        """Test list_accounts tool."""
        from ripplecast.server import list_accounts

        with patch("ripplecast.server.get_platform_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_account_status = AsyncMock(
                return_value=[
                    {
                        "name": "test-mastodon",
                        "platform": "mastodon",
                        "display_name": "Mastodon",
                        "connected": True,
                        "username": "@test@mastodon.social",
                    },
                    {
                        "name": "test-bluesky",
                        "platform": "bluesky",
                        "display_name": "Bluesky",
                        "connected": False,
                        "error": "Not authenticated",
                    },
                ]
            )
            mock_get_manager.return_value = mock_manager

            result = await list_accounts()

            assert "accounts" in result
            assert len(result["accounts"]) == 2
            assert result["accounts"][0]["name"] == "test-mastodon"
            assert result["accounts"][0]["connected"] is True

    @pytest.mark.asyncio
    async def test_get_posts_success(self, sample_mastodon_posts):
        """Test get_posts tool with successful response."""
        from ripplecast.server import get_posts

        with patch("ripplecast.server.get_platform_manager") as mock_get_manager:
            mock_plugin = MagicMock()
            mock_plugin.connected = True
            mock_plugin.get_current_user = AsyncMock(
                return_value={"username": "@test@mastodon.social"}
            )

            mock_manager = MagicMock()
            mock_manager.get_account.return_value = mock_plugin
            mock_manager.get_account_platform.return_value = "mastodon"
            mock_manager.get_posts = AsyncMock(return_value=sample_mastodon_posts)
            mock_get_manager.return_value = mock_manager

            result = await get_posts(account="test-mastodon", limit=20)

            assert result["success"] is True
            assert result["account"] == "test-mastodon"
            assert result["platform"] == "mastodon"
            assert result["post_count"] == 3

    @pytest.mark.asyncio
    async def test_get_posts_not_connected(self):
        """Test get_posts when account is not connected."""
        from ripplecast.server import get_posts

        with patch("ripplecast.server.get_platform_manager") as mock_get_manager:
            mock_plugin = MagicMock()
            mock_plugin.connected = False

            mock_manager = MagicMock()
            mock_manager.get_account.return_value = mock_plugin
            mock_manager.get_account_platform.return_value = "mastodon"
            mock_get_manager.return_value = mock_manager

            result = await get_posts(account="test-mastodon")

            assert result["success"] is False
            assert result["error"] == "account_not_connected"

    @pytest.mark.asyncio
    async def test_cross_post_success(self, sample_mastodon_post):
        """Test cross_post tool with successful response."""
        from ripplecast.server import cross_post

        with patch("ripplecast.server.get_platform_manager") as mock_get_manager:
            # Source plugin
            mock_source = MagicMock()
            mock_source.connected = True
            mock_source.get_post_by_id = AsyncMock(return_value=sample_mastodon_post)

            # Target plugin
            mock_target = MagicMock()
            mock_target.connected = True
            mock_target.max_post_length = 300
            mock_target.validate_post_content.return_value = (True, None)
            mock_target.create_post = AsyncMock(
                return_value=MagicMock(
                    id="new123",
                    url="https://bsky.app/post/new123",
                )
            )

            mock_manager = MagicMock()
            mock_manager.get_account.side_effect = lambda a: (
                mock_source if a == "test-mastodon" else mock_target
            )
            mock_manager.get_account_platform.side_effect = lambda a: (
                "mastodon" if a == "test-mastodon" else "bluesky"
            )
            mock_get_manager.return_value = mock_manager

            result = await cross_post(
                source_account="test-mastodon",
                post_id="123456789",
                target_account="test-bluesky",
            )

            assert result["success"] is True
            assert result["source"]["account"] == "test-mastodon"
            assert result["target"]["account"] == "test-bluesky"

    @pytest.mark.asyncio
    async def test_cross_post_text_too_long(self, sample_mastodon_post):
        """Test cross_post when text exceeds target limit."""
        from ripplecast.server import cross_post

        # Make the post text too long for Bluesky
        sample_mastodon_post.text = "x" * 350

        with patch("ripplecast.server.get_platform_manager") as mock_get_manager:
            mock_source = MagicMock()
            mock_source.connected = True
            mock_source.get_post_by_id = AsyncMock(return_value=sample_mastodon_post)

            mock_target = MagicMock()
            mock_target.connected = True
            mock_target.max_post_length = 300
            mock_target.validate_post_content.return_value = (
                False,
                "Post exceeds 300 characters",
            )

            mock_manager = MagicMock()
            mock_manager.get_account.side_effect = lambda a: (
                mock_source if a == "test-mastodon" else mock_target
            )
            mock_manager.get_account_platform.side_effect = lambda a: (
                "mastodon" if a == "test-mastodon" else "bluesky"
            )
            mock_get_manager.return_value = mock_manager

            result = await cross_post(
                source_account="test-mastodon",
                post_id="123456789",
                target_account="test-bluesky",
            )

            assert result["success"] is False
            assert result["error"] == "text_too_long"
            assert "suggested_truncation" in result

    @pytest.mark.asyncio
    async def test_bulk_cross_post_dry_run(self, sample_mastodon_post):
        """Test bulk_cross_post in dry run mode."""
        from ripplecast.server import bulk_cross_post

        with patch("ripplecast.server.get_platform_manager") as mock_get_manager:
            mock_source = MagicMock()
            mock_source.connected = True
            mock_source.get_post_by_id = AsyncMock(return_value=sample_mastodon_post)

            mock_target = MagicMock()
            mock_target.connected = True
            mock_target.max_post_length = 300
            mock_target.validate_post_content.return_value = (True, None)

            mock_manager = MagicMock()
            mock_manager.get_account.side_effect = lambda a: (
                mock_source if a == "test-mastodon" else mock_target
            )
            mock_manager.get_account_platform.side_effect = lambda a: (
                "mastodon" if a == "test-mastodon" else "bluesky"
            )
            mock_get_manager.return_value = mock_manager

            posts = [
                {
                    "source_account": "test-mastodon",
                    "post_id": "123",
                    "target_account": "test-bluesky",
                }
            ]

            result = await bulk_cross_post(posts=posts, dry_run=True)

            assert result["dry_run"] is True
            assert result["total"] == 1
            assert result["results"][0]["status"] == "would_succeed"


class TestGetSyncStatus:
    """Tests for get_sync_status tool — Signal 1 and Signal 2."""

    def _make_manager(self, source_post, target_posts, matches, via_ripplecast=False):
        """Build a mock platform manager for get_sync_status tests."""
        mock_source = MagicMock()
        mock_source.connected = True
        mock_source.get_post_by_id = AsyncMock(return_value=source_post)
        mock_source.is_posted_via_ripplecast = MagicMock(return_value=via_ripplecast)

        mock_target = MagicMock()
        mock_target.connected = True

        mock_manager = MagicMock()
        mock_manager.get_account.side_effect = lambda a: (
            mock_source if a == "test-mastodon" else mock_target
        )
        mock_manager.get_account_platform.side_effect = lambda a: (
            "mastodon" if a == "test-mastodon" else "bluesky"
        )
        mock_manager.get_all_accounts.return_value = {
            "test-mastodon": mock_source,
            "test-bluesky": mock_target,
        }
        mock_manager.get_posts = AsyncMock(return_value=target_posts)
        return mock_manager

    @pytest.mark.asyncio
    async def test_signal1_content_match_regardless_of_timestamp_order(self):
        """Signal 1: content match is found even when target post predates source post."""
        from ripplecast.server import get_sync_status

        # Bluesky post was published BEFORE the Mastodon post
        source_post = Post(
            id="111",
            platform="mastodon",
            account="test-mastodon",
            text="Hello world! Cross-platform post.",
            created_at=datetime(2025, 2, 13, 10, 0, 0, tzinfo=timezone.utc),
            url="https://mastodon.social/@testuser/111",
        )
        older_bluesky_post = Post(
            id="at://did:plc:test/app.bsky.feed.post/aaa",
            platform="bluesky",
            account="test-bluesky",
            text="Hello world! Cross-platform post.",
            created_at=datetime(2025, 2, 1, 10, 0, 0, tzinfo=timezone.utc),  # 12 days earlier
            url="https://bsky.app/profile/test.bsky.social/post/aaa",
        )

        mock_manager = self._make_manager(
            source_post,
            [older_bluesky_post],
            matches=[],
        )

        mock_ctx = MagicMock()
        expected_match = PostMatch(
            post_a_id="111",
            post_b_id="at://did:plc:test/app.bsky.feed.post/aaa",
            confidence=0.95,
            reason="identical text",
        )

        with patch("ripplecast.server.get_platform_manager", return_value=mock_manager), patch(
            "ripplecast.server.match_posts_with_llm", AsyncMock(return_value=[expected_match])
        ):
            result = await get_sync_status(
                account="test-mastodon",
                post_id="111",
                ctx=mock_ctx,
            )

        assert result["success"] is True
        assert len(result["synced_to"]) == 1
        assert result["synced_to"][0]["account"] == "test-bluesky"
        assert result["synced_to"][0]["post_id"] == "at://did:plc:test/app.bsky.feed.post/aaa"
        assert result["not_synced_to"] == []

    @pytest.mark.asyncio
    async def test_signal2_mastodon_application_metadata(self):
        """Signal 2: Mastodon post with application.name='ripplecast' is considered synced."""
        from ripplecast.server import get_sync_status

        source_post = Post(
            id="222",
            platform="mastodon",
            account="test-mastodon",
            text="A post created via ripplecast.",
            created_at=datetime(2025, 2, 13, 10, 0, 0, tzinfo=timezone.utc),
            url="https://mastodon.social/@testuser/222",
            raw_data={"application": {"name": "ripplecast", "website": None}},
        )

        mock_manager = self._make_manager(source_post, [], matches=[], via_ripplecast=True)
        mock_ctx = MagicMock()

        with patch("ripplecast.server.get_platform_manager", return_value=mock_manager), patch(
            "ripplecast.server.match_posts_with_llm", AsyncMock(return_value=[])
        ):
            result = await get_sync_status(
                account="test-mastodon",
                post_id="222",
                ctx=mock_ctx,
            )

        assert result["success"] is True
        assert len(result["synced_to"]) == 1
        assert result["synced_to"][0]["account"] == "test-bluesky"
        assert result["synced_to"][0]["match_type"] == "posted_via_ripplecast"
        assert result["not_synced_to"] == []

    @pytest.mark.asyncio
    async def test_signal2_bluesky_via_metadata(self):
        """Signal 2: Bluesky post with raw_data via='ripplecast' is considered synced."""
        from ripplecast.server import get_sync_status

        source_post = Post(
            id="at://did:plc:test/app.bsky.feed.post/bbb",
            platform="bluesky",
            account="test-bluesky",
            text="A post created via ripplecast.",
            created_at=datetime(2025, 2, 13, 10, 0, 0, tzinfo=timezone.utc),
            url="https://bsky.app/profile/test.bsky.social/post/bbb",
            raw_data={"uri": "at://did:plc:test/app.bsky.feed.post/bbb", "cid": "abc", "via": "ripplecast"},
        )

        mock_source = MagicMock()
        mock_source.connected = True
        mock_source.get_post_by_id = AsyncMock(return_value=source_post)

        mock_target = MagicMock()
        mock_target.connected = True

        mock_manager = MagicMock()
        mock_manager.get_account.side_effect = lambda a: (
            mock_target if a == "test-mastodon" else mock_source
        )
        mock_manager.get_account_platform.side_effect = lambda a: (
            "mastodon" if a == "test-mastodon" else "bluesky"
        )
        mock_manager.get_all_accounts.return_value = {
            "test-mastodon": mock_target,
            "test-bluesky": mock_source,
        }
        mock_manager.get_posts = AsyncMock(return_value=[])

        mock_ctx = MagicMock()

        with patch("ripplecast.server.get_platform_manager", return_value=mock_manager), patch(
            "ripplecast.server.match_posts_with_llm", AsyncMock(return_value=[])
        ):
            result = await get_sync_status(
                account="test-bluesky",
                post_id="at://did:plc:test/app.bsky.feed.post/bbb",
                ctx=mock_ctx,
            )

        assert result["success"] is True
        assert len(result["synced_to"]) == 1
        assert result["synced_to"][0]["account"] == "test-mastodon"
        assert result["synced_to"][0]["match_type"] == "posted_via_ripplecast"
        assert result["not_synced_to"] == []

    @pytest.mark.asyncio
    async def test_no_match_and_no_ripplecast_signal_is_unsynced(self):
        """A post with no content match and no ripplecast signal remains unsynced."""
        from ripplecast.server import get_sync_status

        source_post = Post(
            id="333",
            platform="mastodon",
            account="test-mastodon",
            text="Only on Mastodon, not synced anywhere.",
            created_at=datetime(2025, 2, 13, 10, 0, 0, tzinfo=timezone.utc),
            url="https://mastodon.social/@testuser/333",
        )

        mock_manager = self._make_manager(source_post, [], matches=[])
        mock_ctx = MagicMock()

        with patch("ripplecast.server.get_platform_manager", return_value=mock_manager), patch(
            "ripplecast.server.match_posts_with_llm", AsyncMock(return_value=[])
        ):
            result = await get_sync_status(
                account="test-mastodon",
                post_id="333",
                ctx=mock_ctx,
            )

        assert result["success"] is True
        assert result["synced_to"] == []
        assert "test-bluesky" in result["not_synced_to"]


class TestFindUnsyncedPosts:
    """Tests for find_unsynced_posts tool — Signal 2 filtering."""

    @pytest.mark.asyncio
    async def test_signal2_removes_ripplecast_posts_from_unsynced(self):
        """Posts created via ripplecast are not reported as unsynced."""
        from ripplecast.server import find_unsynced_posts

        mastodon_post = Post(
            id="111",
            platform="mastodon",
            account="test-mastodon",
            text="A post created via ripplecast.",
            created_at=datetime(2026, 2, 17, 10, 0, 0, tzinfo=timezone.utc),
            url="https://mastodon.social/@testuser/111",
            raw_data={"application": {"name": "ripplecast"}},
        )

        mock_mastodon_plugin = MagicMock()
        mock_mastodon_plugin.connected = True
        mock_mastodon_plugin.is_posted_via_ripplecast = MagicMock(return_value=True)

        mock_bluesky_plugin = MagicMock()
        mock_bluesky_plugin.connected = True
        mock_bluesky_plugin.is_posted_via_ripplecast = MagicMock(return_value=False)

        mock_manager = MagicMock()
        mock_manager.get_account_platform.side_effect = lambda a: (
            "mastodon" if a == "test-mastodon" else "bluesky"
        )
        mock_manager.get_account.side_effect = lambda a: (
            mock_mastodon_plugin if a == "test-mastodon" else mock_bluesky_plugin
        )
        mock_manager.get_all_posts = AsyncMock(
            return_value={
                "test-mastodon": [mastodon_post],
                "test-bluesky": [],
            }
        )

        mock_ctx = MagicMock()

        with patch("ripplecast.server.get_platform_manager", return_value=mock_manager), patch(
            "ripplecast.server.match_posts_with_llm", AsyncMock(return_value=[])
        ):
            result = await find_unsynced_posts(ctx=mock_ctx, days_back=30)

        assert result["success"] is True
        assert result["unsynced"]["mastodon_only"] == []
        assert len(result["already_synced_via_ripplecast"]) == 1
        assert result["already_synced_via_ripplecast"][0]["post_id"] == "111"
        assert result["already_synced_via_ripplecast"][0]["match_type"] == "posted_via_ripplecast"


class TestIsPostedViaRipplecast:
    """Unit tests for is_posted_via_ripplecast on each platform plugin."""

    def _mastodon_post(self, raw_data=None):
        from ripplecast.config import MastodonConfig
        from ripplecast.platforms.mastodon import MastodonPlugin

        plugin = MastodonPlugin(MastodonConfig(instance_url="https://mastodon.social", access_token="tok"))
        post = Post(
            id="x",
            platform="mastodon",
            text="test",
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            url="https://mastodon.social/x",
            raw_data=raw_data or {},
        )
        return plugin, post

    def _bluesky_post(self, raw_data=None):
        from ripplecast.config import BlueskyConfig
        from ripplecast.platforms.bluesky import BlueskyPlugin

        plugin = BlueskyPlugin(BlueskyConfig(handle="test.bsky.social", app_password="xxxx"))
        post = Post(
            id="at://did:plc:test/app.bsky.feed.post/x",
            platform="bluesky",
            text="test",
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            url="https://bsky.app/profile/test.bsky.social/post/x",
            raw_data=raw_data or {},
        )
        return plugin, post

    def test_mastodon_application_name_ripplecast(self):
        plugin, post = self._mastodon_post({"application": {"name": "ripplecast"}})
        assert plugin.is_posted_via_ripplecast(post) is True

    def test_mastodon_application_name_case_insensitive(self):
        plugin, post = self._mastodon_post({"application": {"name": "Ripplecast"}})
        assert plugin.is_posted_via_ripplecast(post) is True

    def test_mastodon_application_name_other_app(self):
        plugin, post = self._mastodon_post({"application": {"name": "Toot!"}})
        assert plugin.is_posted_via_ripplecast(post) is False

    def test_mastodon_no_application_field(self):
        plugin, post = self._mastodon_post({})
        assert plugin.is_posted_via_ripplecast(post) is False

    def test_bluesky_via_field_ripplecast(self):
        plugin, post = self._bluesky_post({"uri": "at://...", "cid": "abc", "via": "ripplecast"})
        assert plugin.is_posted_via_ripplecast(post) is True

    def test_bluesky_no_via_field(self):
        plugin, post = self._bluesky_post({"uri": "at://...", "cid": "abc"})
        assert plugin.is_posted_via_ripplecast(post) is False
