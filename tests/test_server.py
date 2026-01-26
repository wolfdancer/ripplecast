"""Tests for the MCP server tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestServerTools:
    """Tests for MCP server tool functions."""

    @pytest.mark.asyncio
    async def test_list_platforms(self):
        """Test list_platforms tool."""
        from ripplecast.server import list_platforms

        with patch("ripplecast.server.get_platform_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.get_platform_status.return_value = [
                {
                    "name": "mastodon",
                    "display_name": "Mastodon",
                    "connected": True,
                    "username": "@test@mastodon.social",
                },
                {
                    "name": "bluesky",
                    "display_name": "Bluesky",
                    "connected": False,
                    "error": "Not authenticated",
                },
            ]
            mock_get_manager.return_value = mock_manager

            result = await list_platforms()

            assert "platforms" in result
            assert len(result["platforms"]) == 2
            assert result["platforms"][0]["name"] == "mastodon"
            assert result["platforms"][0]["connected"] is True

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

            mock_manager = AsyncMock()
            mock_manager.get_platform.return_value = mock_plugin
            mock_manager.get_posts.return_value = sample_mastodon_posts
            mock_get_manager.return_value = mock_manager

            result = await get_posts(platform="mastodon", limit=20)

            assert result["success"] is True
            assert result["platform"] == "mastodon"
            assert result["post_count"] == 3

    @pytest.mark.asyncio
    async def test_get_posts_not_connected(self):
        """Test get_posts when platform is not connected."""
        from ripplecast.server import get_posts

        with patch("ripplecast.server.get_platform_manager") as mock_get_manager:
            mock_plugin = MagicMock()
            mock_plugin.connected = False

            mock_manager = AsyncMock()
            mock_manager.get_platform.return_value = mock_plugin
            mock_get_manager.return_value = mock_manager

            result = await get_posts(platform="mastodon")

            assert result["success"] is False
            assert result["error"] == "platform_not_connected"

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
            mock_target.validate_post_content.return_value = (True, None)
            mock_target.create_post = AsyncMock(
                return_value=MagicMock(
                    id="new123",
                    url="https://bsky.app/post/new123",
                )
            )

            mock_manager = AsyncMock()
            mock_manager.get_platform.side_effect = lambda p: (
                mock_source if p == "mastodon" else mock_target
            )
            mock_get_manager.return_value = mock_manager

            result = await cross_post(
                source_platform="mastodon",
                post_id="123456789",
                target_platform="bluesky",
            )

            assert result["success"] is True
            assert result["source"]["platform"] == "mastodon"
            assert result["target"]["platform"] == "bluesky"

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

            mock_manager = AsyncMock()
            mock_manager.get_platform.side_effect = lambda p: (
                mock_source if p == "mastodon" else mock_target
            )
            mock_get_manager.return_value = mock_manager

            result = await cross_post(
                source_platform="mastodon",
                post_id="123456789",
                target_platform="bluesky",
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
            mock_target.validate_post_content.return_value = (True, None)

            mock_manager = AsyncMock()
            mock_manager.get_platform.side_effect = lambda p: (
                mock_source if p == "mastodon" else mock_target
            )
            mock_get_manager.return_value = mock_manager

            posts = [
                {
                    "source_platform": "mastodon",
                    "post_id": "123",
                    "target_platform": "bluesky",
                }
            ]

            result = await bulk_cross_post(posts=posts, dry_run=True)

            assert result["dry_run"] is True
            assert result["total"] == 1
            assert result["results"][0]["status"] == "would_succeed"
