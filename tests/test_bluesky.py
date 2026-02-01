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


class TestExpandFacetsInText:
    """Tests for expanding Bluesky facets into full URLs."""

    def test_expand_facets_no_facets(self):
        """Test with no facets returns original text."""
        text = "Hello world!"
        result = BlueskyPlugin._expand_facets_in_text(text, None)
        assert result == text

    def test_expand_facets_empty_facets(self):
        """Test with empty facets list returns original text."""
        text = "Hello world!"
        result = BlueskyPlugin._expand_facets_in_text(text, [])
        assert result == text

    def test_expand_facets_single_link(self):
        """Test expanding a single truncated URL."""

        class MockFeature:
            uri = "https://github.com/wolfdancer/ripplecast/pull/5"

        class MockIndex:
            byte_start = 10
            byte_end = 35  # "github.com/wolfdancer/r..."

        class MockFacet:
            index = MockIndex()
            features = [MockFeature()]

        text = "Check out github.com/wolfdancer/r... for updates!"
        facets = [MockFacet()]

        result = BlueskyPlugin._expand_facets_in_text(text, facets)

        assert "https://github.com/wolfdancer/ripplecast/pull/5" in result
        assert "github.com/wolfdancer/r..." not in result

    def test_expand_facets_multiple_links(self):
        """Test expanding multiple truncated URLs."""

        class MockFeature1:
            uri = "https://example.com/first-link"

        class MockIndex1:
            byte_start = 0
            byte_end = 11  # "example.com"

        class MockFacet1:
            index = MockIndex1()
            features = [MockFeature1()]

        class MockFeature2:
            uri = "https://other.com/second-link"

        class MockIndex2:
            byte_start = 16
            byte_end = 25  # "other.com"

        class MockFacet2:
            index = MockIndex2()
            features = [MockFeature2()]

        text = "example.com and other.com are cool"
        facets = [MockFacet1(), MockFacet2()]

        result = BlueskyPlugin._expand_facets_in_text(text, facets)

        assert "https://example.com/first-link" in result
        assert "https://other.com/second-link" in result

    def test_expand_facets_handles_unicode(self):
        """Test that byte offsets work correctly with unicode text."""

        class MockFeature:
            uri = "https://example.com/link"

        class MockIndex:
            # After "Hello 🌍 " which is 10 bytes in UTF-8 (H=1, e=1, l=1, l=1, o=1, space=1, emoji=4, space=1)
            byte_start = 10
            byte_end = 21  # "example.com"

        class MockFacet:
            index = MockIndex()
            features = [MockFeature()]

        text = "Hello 🌍 example.com test"
        facets = [MockFacet()]

        result = BlueskyPlugin._expand_facets_in_text(text, facets)

        assert "https://example.com/link" in result
        assert "Hello 🌍" in result

    def test_expand_facets_ignores_non_link_facets(self):
        """Test that non-link facets (e.g., mentions) are ignored."""

        class MockMentionFeature:
            # This is a mention facet, no 'uri' attribute
            did = "did:plc:example123"

        class MockIndex:
            byte_start = 0
            byte_end = 5

        class MockFacet:
            index = MockIndex()
            features = [MockMentionFeature()]

        text = "@user hello"
        facets = [MockFacet()]

        result = BlueskyPlugin._expand_facets_in_text(text, facets)

        # Text should remain unchanged since it's not a link facet
        assert result == text
