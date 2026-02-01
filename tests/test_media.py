"""Tests for media transfer utilities."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ripplecast.media import (
    MAX_MEDIA_SIZE_MB,
    SUPPORTED_IMAGE_TYPES,
    SUPPORTED_VIDEO_TYPES,
    DownloadedMedia,
    download_media,
    download_thumbnail,
)
from ripplecast.models import MediaAttachment


class TestDownloadedMedia:
    """Tests for the DownloadedMedia dataclass."""

    def test_is_image_true(self):
        """Test that JPEG is detected as image."""
        media = DownloadedMedia(
            data=b"fake data",
            mime_type="image/jpeg",
            alt_text="Test",
            original_url="https://example.com/img.jpg",
        )
        assert media.is_image is True
        assert media.is_video is False

    def test_is_image_for_all_types(self):
        """Test all supported image types."""
        for mime in SUPPORTED_IMAGE_TYPES:
            media = DownloadedMedia(
                data=b"data",
                mime_type=mime,
                alt_text=None,
                original_url="https://example.com/img",
            )
            assert media.is_image is True

    def test_is_video_true(self):
        """Test that MP4 is detected as video."""
        media = DownloadedMedia(
            data=b"fake video data",
            mime_type="video/mp4",
            alt_text="Video",
            original_url="https://example.com/video.mp4",
        )
        assert media.is_video is True
        assert media.is_image is False

    def test_is_video_for_all_types(self):
        """Test all supported video types."""
        for mime in SUPPORTED_VIDEO_TYPES:
            media = DownloadedMedia(
                data=b"data",
                mime_type=mime,
                alt_text=None,
                original_url="https://example.com/video",
            )
            assert media.is_video is True

    def test_file_size(self):
        """Test file_size property."""
        data = b"x" * 1000
        media = DownloadedMedia(
            data=data,
            mime_type="image/png",
            alt_text=None,
            original_url="https://example.com/img.png",
        )
        assert media.file_size == 1000


class TestDownloadMedia:
    """Tests for the download_media function."""

    @pytest.mark.asyncio
    async def test_download_media_success(self):
        """Test successful media download."""
        attachment = MediaAttachment(
            url="https://example.com/image.jpg",
            media_type="image",
            alt_text="Test image",
            mime_type="image/jpeg",
        )

        mock_response = MagicMock()
        mock_response.content = b"fake image data"
        mock_response.headers = {"content-type": "image/jpeg"}
        mock_response.raise_for_status = MagicMock()

        with patch("ripplecast.media.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await download_media(attachment)

            assert result is not None
            assert result.data == b"fake image data"
            assert result.mime_type == "image/jpeg"
            assert result.alt_text == "Test image"
            assert result.original_url == "https://example.com/image.jpg"

    @pytest.mark.asyncio
    async def test_download_media_uses_attachment_mime_type(self):
        """Test that attachment mime_type is preferred over Content-Type header."""
        attachment = MediaAttachment(
            url="https://example.com/image.jpg",
            media_type="image",
            alt_text=None,
            mime_type="image/png",  # Explicit mime type
        )

        mock_response = MagicMock()
        mock_response.content = b"data"
        mock_response.headers = {"content-type": "application/octet-stream"}
        mock_response.raise_for_status = MagicMock()

        with patch("ripplecast.media.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await download_media(attachment)

            assert result is not None
            assert result.mime_type == "image/png"

    @pytest.mark.asyncio
    async def test_download_media_too_large(self):
        """Test that large media is rejected."""
        attachment = MediaAttachment(
            url="https://example.com/large.jpg",
            media_type="image",
        )

        # Create data larger than MAX_MEDIA_SIZE_MB
        large_data = b"x" * (MAX_MEDIA_SIZE_MB * 1024 * 1024 + 1)

        mock_response = MagicMock()
        mock_response.content = large_data
        mock_response.headers = {"content-type": "image/jpeg"}
        mock_response.raise_for_status = MagicMock()

        with patch("ripplecast.media.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await download_media(attachment)

            assert result is None

    @pytest.mark.asyncio
    async def test_download_media_http_error(self):
        """Test that HTTP errors are handled gracefully."""
        attachment = MediaAttachment(
            url="https://example.com/missing.jpg",
            media_type="image",
        )

        with patch("ripplecast.media.httpx.AsyncClient") as mock_client:
            import httpx
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.HTTPStatusError(
                    "Not Found", request=MagicMock(), response=MagicMock()
                )
            )

            result = await download_media(attachment)

            assert result is None

    @pytest.mark.asyncio
    async def test_download_media_request_error(self):
        """Test that request errors are handled gracefully."""
        attachment = MediaAttachment(
            url="https://unreachable.example.com/image.jpg",
            media_type="image",
        )

        with patch("ripplecast.media.httpx.AsyncClient") as mock_client:
            import httpx
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.RequestError("Connection failed")
            )

            result = await download_media(attachment)

            assert result is None


class TestDownloadThumbnail:
    """Tests for the download_thumbnail function."""

    @pytest.mark.asyncio
    async def test_download_thumbnail_success(self):
        """Test successful thumbnail download."""
        mock_response = MagicMock()
        mock_response.content = b"thumbnail data"
        mock_response.raise_for_status = MagicMock()

        with patch("ripplecast.media.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await download_thumbnail("https://example.com/thumb.jpg")

            assert result == b"thumbnail data"

    @pytest.mark.asyncio
    async def test_download_thumbnail_failure(self):
        """Test that thumbnail download failure returns None."""
        with patch("ripplecast.media.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("Download failed")
            )

            result = await download_thumbnail("https://example.com/thumb.jpg")

            assert result is None
