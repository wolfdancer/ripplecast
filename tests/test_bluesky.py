"""Tests for Bluesky platform plugin."""

import pytest

from ripplecast.models import AuthenticationError
from ripplecast.platforms.bluesky import BlueskyPlugin


class TestBlueskyPlugin:
    """Tests for the BlueskyPlugin class."""

    def test_platform_properties(self, bluesky_config):
        """Test platform property values."""
        plugin = BlueskyPlugin(bluesky_config)

        assert plugin.platform_name == "bluesky"
        assert plugin.display_name == "Bluesky"
        assert plugin.max_post_length == 300
        assert plugin.connected is False

    @pytest.mark.asyncio
    async def test_authenticate_success(self, bluesky_config, mock_bluesky_client):
        """Test successful authentication."""
        plugin = BlueskyPlugin(bluesky_config)

        result = await plugin.authenticate()

        assert result is True
        assert plugin.connected is True

    @pytest.mark.asyncio
    async def test_authenticate_not_configured(self):
        """Test authentication with missing config."""
        from ripplecast.config import BlueskyConfig

        config = BlueskyConfig(handle="", app_password="")
        plugin = BlueskyPlugin(config)

        result = await plugin.authenticate()

        assert result is False
        assert plugin.connected is False

    @pytest.mark.asyncio
    async def test_get_current_user_not_authenticated(self, bluesky_config):
        """Test getting user when not authenticated."""
        plugin = BlueskyPlugin(bluesky_config)

        with pytest.raises(AuthenticationError):
            await plugin.get_current_user()

    def test_validate_post_content_valid(self, bluesky_config):
        """Test validating valid post content."""
        plugin = BlueskyPlugin(bluesky_config)

        is_valid, error = plugin.validate_post_content("Hello world!")

        assert is_valid is True
        assert error is None

    def test_validate_post_content_too_long(self, bluesky_config):
        """Test validating post that's too long."""
        plugin = BlueskyPlugin(bluesky_config)
        long_text = "x" * 350

        is_valid, error = plugin.validate_post_content(long_text)

        assert is_valid is False
        assert "exceeds 300" in error

    def test_validate_post_at_limit(self, bluesky_config):
        """Test validating post exactly at the limit."""
        plugin = BlueskyPlugin(bluesky_config)
        text = "x" * 300

        is_valid, error = plugin.validate_post_content(text)

        assert is_valid is True
        assert error is None

    def test_uri_to_url(self, bluesky_config):
        """Test converting AT Protocol URI to bsky.app URL."""
        plugin = BlueskyPlugin(bluesky_config)
        uri = "at://did:plc:test123/app.bsky.feed.post/abc456"

        url = plugin._uri_to_url(uri)

        assert "bsky.app/profile" in url
        assert "abc456" in url
