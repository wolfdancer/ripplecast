"""Tests for Mastodon platform plugin."""

from datetime import datetime, timezone

import pytest

from ripplecast.models import AuthenticationError, PostTooLongError
from ripplecast.platforms.mastodon import MastodonPlugin


class TestMastodonPlugin:
    """Tests for the MastodonPlugin class."""

    def test_platform_properties(self, mastodon_config):
        """Test platform property values."""
        plugin = MastodonPlugin(mastodon_config)

        assert plugin.platform_name == "mastodon"
        assert plugin.display_name == "Mastodon"
        assert plugin.max_post_length == 500  # Default before auth
        assert plugin.connected is False

    @pytest.mark.asyncio
    async def test_authenticate_success(self, mastodon_config, mock_mastodon_client):
        """Test successful authentication."""
        plugin = MastodonPlugin(mastodon_config)

        result = await plugin.authenticate()

        assert result is True
        assert plugin.connected is True

    @pytest.mark.asyncio
    async def test_authenticate_not_configured(self):
        """Test authentication with missing config."""
        from ripplecast.config import MastodonConfig

        config = MastodonConfig(instance_url="", access_token="")
        plugin = MastodonPlugin(config)

        result = await plugin.authenticate()

        assert result is False
        assert plugin.connected is False

    @pytest.mark.asyncio
    async def test_get_current_user_not_authenticated(self, mastodon_config):
        """Test getting user when not authenticated."""
        plugin = MastodonPlugin(mastodon_config)

        with pytest.raises(AuthenticationError):
            await plugin.get_current_user()

    def test_validate_post_content_valid(self, mastodon_config):
        """Test validating valid post content."""
        plugin = MastodonPlugin(mastodon_config)

        is_valid, error = plugin.validate_post_content("Hello world!")

        assert is_valid is True
        assert error is None

    def test_validate_post_content_too_long(self, mastodon_config):
        """Test validating post that's too long."""
        plugin = MastodonPlugin(mastodon_config)
        long_text = "x" * 600

        is_valid, error = plugin.validate_post_content(long_text)

        assert is_valid is False
        assert "exceeds 500" in error

    def test_status_to_post_basic(self, mastodon_config):
        """Test converting Mastodon status to Post."""
        plugin = MastodonPlugin(mastodon_config)
        status = {
            "id": "123",
            "content": "<p>Hello world!</p>",
            "created_at": datetime(2025, 1, 25, 10, 0, 0, tzinfo=timezone.utc),
            "url": "https://mastodon.social/@user/123",
            "reblog": None,
            "media_attachments": [],
            "in_reply_to_id": None,
            "language": "en",
        }

        post = plugin._status_to_post(status)

        assert post.id == "123"
        assert post.platform == "mastodon"
        assert post.text == "Hello world!"
        assert post.url == "https://mastodon.social/@user/123"
        assert post.is_repost is False
        assert post.language == "en"

    def test_status_to_post_with_html_entities(self, mastodon_config):
        """Test converting status with HTML entities."""
        plugin = MastodonPlugin(mastodon_config)
        status = {
            "id": "456",
            "content": "<p>This &amp; that &lt;tag&gt; &quot;quoted&quot;</p>",
            "created_at": datetime.now(timezone.utc),
            "url": "https://mastodon.social/@user/456",
            "reblog": None,
            "media_attachments": [],
            "in_reply_to_id": None,
            "language": None,
        }

        post = plugin._status_to_post(status)

        assert post.text == 'This & that <tag> "quoted"'

    def test_status_to_post_reblog(self, mastodon_config):
        """Test converting a reblog status."""
        plugin = MastodonPlugin(mastodon_config)
        status = {
            "id": "789",
            "content": "",
            "created_at": datetime.now(timezone.utc),
            "url": "https://mastodon.social/@user/789",
            "reblog": {
                "id": "original123",
                "content": "<p>Original post content</p>",
            },
            "media_attachments": [],
            "in_reply_to_id": None,
            "language": None,
        }

        post = plugin._status_to_post(status)

        assert post.is_repost is True
        assert post.original_post_id == "original123"
        assert post.text == "Original post content"
