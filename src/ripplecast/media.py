"""Media transfer utilities for cross-posting."""

import logging
from dataclasses import dataclass

import httpx

from ripplecast.models import MediaAttachment

logger = logging.getLogger(__name__)

# Supported media types for cross-posting
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
SUPPORTED_VIDEO_TYPES = {"video/mp4", "video/webm"}
MAX_MEDIA_SIZE_MB = 10


@dataclass
class DownloadedMedia:
    """Media downloaded from source platform."""

    data: bytes
    mime_type: str
    alt_text: str | None
    original_url: str

    @property
    def is_image(self) -> bool:
        """Check if this is a supported image type."""
        return self.mime_type in SUPPORTED_IMAGE_TYPES

    @property
    def is_video(self) -> bool:
        """Check if this is a supported video type."""
        return self.mime_type in SUPPORTED_VIDEO_TYPES

    @property
    def file_size(self) -> int:
        """Get the file size in bytes."""
        return len(self.data)


async def download_media(attachment: MediaAttachment) -> DownloadedMedia | None:
    """
    Download media from a URL.

    Args:
        attachment: The media attachment to download

    Returns:
        DownloadedMedia if successful, None otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(attachment.url)
            response.raise_for_status()

            data = response.content
            content_type = response.headers.get("content-type", "")
            mime_type = attachment.mime_type or content_type.split(";")[0].strip()

            if len(data) > MAX_MEDIA_SIZE_MB * 1024 * 1024:
                logger.warning(f"Media too large: {len(data)} bytes from {attachment.url}")
                return None

            return DownloadedMedia(
                data=data,
                mime_type=mime_type,
                alt_text=attachment.alt_text,
                original_url=attachment.url,
            )

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error downloading media from {attachment.url}: {e}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Request error downloading media from {attachment.url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error downloading media: {e}")
        return None


async def download_thumbnail(url: str) -> bytes | None:
    """
    Download a thumbnail image for link embeds.

    Args:
        url: The thumbnail URL to download

    Returns:
        Thumbnail bytes if successful, None otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
    except Exception as e:
        logger.warning(f"Failed to download thumbnail from {url}: {e}")
        return None
