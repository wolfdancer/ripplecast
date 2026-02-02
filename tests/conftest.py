"""Pytest configuration and shared fixtures."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from ripplecast.config import AccountConfig, BlueskyConfig, MastodonConfig
from ripplecast.models import Post


@pytest.fixture
def mastodon_config():
    """Create a test Mastodon config."""
    return MastodonConfig(
        instance_url="https://mastodon.social",
        access_token="test_token",
    )


@pytest.fixture
def bluesky_config():
    """Create a test Bluesky config."""
    return BlueskyConfig(
        handle="test.bsky.social",
        app_password="xxxx-xxxx-xxxx-xxxx",
    )


@pytest.fixture
def mastodon_account_config():
    """Create a test Mastodon account config."""
    return AccountConfig(
        name="test-mastodon",
        platform="mastodon",
        credentials={
            "instance-url": "https://mastodon.social",
            "access-token": "test_token",
        },
        enabled=True,
    )


@pytest.fixture
def bluesky_account_config():
    """Create a test Bluesky account config."""
    return AccountConfig(
        name="test-bluesky",
        platform="bluesky",
        credentials={
            "handle": "test.bsky.social",
            "app-password": "xxxx-xxxx-xxxx-xxxx",
        },
        enabled=True,
    )


@pytest.fixture
def sample_mastodon_post():
    """Create a sample Mastodon post."""
    return Post(
        id="123456789",
        platform="mastodon",
        account="test-mastodon",
        text="Hello world! This is a test post.",
        created_at=datetime(2025, 1, 25, 10, 0, 0, tzinfo=timezone.utc),
        url="https://mastodon.social/@testuser/123456789",
    )


@pytest.fixture
def sample_bluesky_post():
    """Create a sample Bluesky post."""
    return Post(
        id="at://did:plc:test/app.bsky.feed.post/abc123",
        platform="bluesky",
        account="test-bluesky",
        text="Hello world! This is a test post.",
        created_at=datetime(2025, 1, 25, 10, 2, 0, tzinfo=timezone.utc),
        url="https://bsky.app/profile/test.bsky.social/post/abc123",
    )


@pytest.fixture
def sample_mastodon_posts():
    """Create a list of sample Mastodon posts."""
    return [
        Post(
            id="111",
            platform="mastodon",
            account="test-mastodon",
            text="First post on Mastodon",
            created_at=datetime(2025, 1, 25, 10, 0, 0, tzinfo=timezone.utc),
            url="https://mastodon.social/@testuser/111",
        ),
        Post(
            id="222",
            platform="mastodon",
            account="test-mastodon",
            text="Second post with a link https://example.com",
            created_at=datetime(2025, 1, 24, 15, 30, 0, tzinfo=timezone.utc),
            url="https://mastodon.social/@testuser/222",
        ),
        Post(
            id="333",
            platform="mastodon",
            account="test-mastodon",
            text="Third post only on Mastodon",
            created_at=datetime(2025, 1, 23, 9, 0, 0, tzinfo=timezone.utc),
            url="https://mastodon.social/@testuser/333",
        ),
    ]


@pytest.fixture
def sample_bluesky_posts():
    """Create a list of sample Bluesky posts."""
    return [
        Post(
            id="at://did:plc:test/app.bsky.feed.post/aaa",
            platform="bluesky",
            account="test-bluesky",
            text="First post on Mastodon",  # Same as mastodon post 111
            created_at=datetime(2025, 1, 25, 10, 5, 0, tzinfo=timezone.utc),
            url="https://bsky.app/profile/test.bsky.social/post/aaa",
        ),
        Post(
            id="at://did:plc:test/app.bsky.feed.post/bbb",
            platform="bluesky",
            account="test-bluesky",
            text="Unique post only on Bluesky",
            created_at=datetime(2025, 1, 24, 12, 0, 0, tzinfo=timezone.utc),
            url="https://bsky.app/profile/test.bsky.social/post/bbb",
        ),
    ]


@pytest.fixture
def mock_mastodon_client(mocker):
    """Create a mock Mastodon client."""
    mock = mocker.patch("ripplecast.platforms.mastodon.Mastodon")

    # Set up mock instance
    instance = mock.return_value
    instance.account_verify_credentials.return_value = {
        "id": "12345",
        "username": "testuser",
        "display_name": "Test User",
        "url": "https://mastodon.social/@testuser",
    }
    instance.instance.return_value = {
        "max_toot_chars": 500,
    }
    instance.me.return_value = {"id": "12345"}

    return mock


@pytest.fixture
def mock_bluesky_client(mocker):
    """Create a mock Bluesky client."""
    mock = mocker.patch("ripplecast.platforms.bluesky.Client")

    # Set up mock instance
    instance = mock.return_value
    instance.me = MagicMock()
    instance.me.did = "did:plc:test"

    profile = MagicMock()
    profile.handle = "test.bsky.social"
    profile.display_name = "Test User"
    instance.get_profile.return_value = profile

    return mock


@pytest.fixture
def fixtures_path():
    """Get the path to test fixtures."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture(fixtures_path):
    """Load a JSON fixture file."""

    def _load(name: str) -> dict:
        with open(fixtures_path / f"{name}.json") as f:
            return json.load(f)

    return _load
