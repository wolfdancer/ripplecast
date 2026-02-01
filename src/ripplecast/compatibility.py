"""Cross-post compatibility analysis."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ripplecast.models import Post


class CompatibilityLevel(Enum):
    """Level of compatibility for cross-posting."""

    FULL = "full"  # Everything can be transferred
    PARTIAL = "partial"  # Some content will be lost
    TEXT_ONLY = "text_only"  # Only text can be transferred
    REQUIRES_CHOICE = "requires_choice"  # User must choose between media and embed


@dataclass
class CompatibilityIssue:
    """A specific compatibility issue."""

    category: str  # "text", "media", "embed", "conflict"
    severity: str  # "warning", "error"
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompatibilityReport:
    """Full compatibility report for cross-posting a post."""

    source_platform: str
    target_platform: str
    post_id: str
    level: CompatibilityLevel
    issues: list[CompatibilityIssue] = field(default_factory=list)

    # What can be transferred
    can_transfer_text: bool = True
    can_transfer_media: bool = False
    can_transfer_link_embed: bool = False

    # Conflict detection
    has_both_media_and_embed: bool = False

    # Warnings and suggestions
    text_needs_truncation: bool = False
    suggested_text: str | None = None
    media_transfer_count: int = 0
    media_skipped_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "source_platform": self.source_platform,
            "target_platform": self.target_platform,
            "post_id": self.post_id,
            "level": self.level.value,
            "issues": [
                {
                    "category": i.category,
                    "severity": i.severity,
                    "message": i.message,
                    "details": i.details,
                }
                for i in self.issues
            ],
            "can_transfer": {
                "text": self.can_transfer_text,
                "media": self.can_transfer_media,
                "link_embed": self.can_transfer_link_embed,
            },
            "has_both_media_and_embed": self.has_both_media_and_embed,
            "text_needs_truncation": self.text_needs_truncation,
            "suggested_text": self.suggested_text,
            "media_transfer_count": self.media_transfer_count,
            "media_skipped_count": self.media_skipped_count,
        }


@dataclass
class PlatformLimits:
    """Platform-specific content limits."""

    max_text_length: int
    max_images: int
    max_image_size_mb: int
    max_video_size_mb: int
    supported_image_types: set[str]
    supported_video_types: set[str]
    supports_link_embed: bool
    supports_alt_text: bool


# Platform-specific limits
PLATFORM_LIMITS: dict[str, PlatformLimits] = {
    "bluesky": PlatformLimits(
        max_text_length=300,
        max_images=4,
        max_image_size_mb=1,
        max_video_size_mb=50,
        supported_image_types={"image/jpeg", "image/png", "image/gif", "image/webp"},
        supported_video_types={"video/mp4"},
        supports_link_embed=True,
        supports_alt_text=True,
    ),
    "mastodon": PlatformLimits(
        max_text_length=500,  # Default, can vary by instance
        max_images=4,
        max_image_size_mb=10,
        max_video_size_mb=40,
        supported_image_types={"image/jpeg", "image/png", "image/gif", "image/webp"},
        supported_video_types={"video/mp4", "video/webm"},
        supports_link_embed=True,  # Auto-generated from URL
        supports_alt_text=True,
    ),
}


def analyze_cross_post_compatibility(
    post: Post,
    target_platform: str,
    target_max_length: int | None = None,
) -> CompatibilityReport:
    """
    Analyze compatibility of cross-posting a post to a target platform.

    Args:
        post: The source post to analyze
        target_platform: Target platform name ("mastodon" or "bluesky")
        target_max_length: Optional override for max text length

    Returns:
        CompatibilityReport with detailed analysis
    """
    limits = PLATFORM_LIMITS.get(target_platform, PLATFORM_LIMITS["mastodon"])
    max_length = target_max_length or limits.max_text_length

    report = CompatibilityReport(
        source_platform=post.platform,
        target_platform=target_platform,
        post_id=post.id,
        level=CompatibilityLevel.FULL,
    )

    issues: list[CompatibilityIssue] = []

    # Check text length
    if len(post.text) > max_length:
        report.text_needs_truncation = True
        report.suggested_text = post.text[: max_length - 3] + "..."
        issues.append(
            CompatibilityIssue(
                category="text",
                severity="warning",
                message=f"Text exceeds {target_platform} limit ({len(post.text)} > {max_length})",
                details={
                    "original_length": len(post.text),
                    "max_length": max_length,
                    "overflow": len(post.text) - max_length,
                },
            )
        )

    # Check for both media AND link embed (conflict for Bluesky)
    has_media = len(post.media_attachments) > 0
    has_embed = post.link_embed is not None

    if has_media and has_embed and target_platform == "bluesky":
        report.has_both_media_and_embed = True
        issues.append(
            CompatibilityIssue(
                category="conflict",
                severity="error",
                message="Post has both media and link embed. Bluesky only supports one embed type.",
                details={
                    "media_count": len(post.media_attachments),
                    "has_link_embed": True,
                },
            )
        )
        report.level = CompatibilityLevel.REQUIRES_CHOICE

    # Check media attachments
    if post.media_attachments:
        transferable = 0
        skipped = 0

        for i, media in enumerate(post.media_attachments):
            mime = media.mime_type or "unknown"
            media_type = media.media_type

            if media_type == "image":
                if mime in limits.supported_image_types or mime == "unknown":
                    transferable += 1
                else:
                    skipped += 1
                    issues.append(
                        CompatibilityIssue(
                            category="media",
                            severity="warning",
                            message=f"Image format {mime} may not be supported on {target_platform}",
                            details={"index": i, "mime_type": mime},
                        )
                    )
            elif media_type == "video":
                if mime in limits.supported_video_types:
                    transferable += 1
                else:
                    skipped += 1
                    issues.append(
                        CompatibilityIssue(
                            category="media",
                            severity="warning",
                            message=f"Video format {mime} may not be supported on {target_platform}",
                            details={"index": i, "mime_type": mime},
                        )
                    )
            else:
                # Audio, gif, etc - attempt transfer
                transferable += 1

        if transferable > 0:
            report.can_transfer_media = True
            report.media_transfer_count = min(transferable, limits.max_images)
            report.media_skipped_count = skipped

        if len(post.media_attachments) > limits.max_images:
            extra = len(post.media_attachments) - limits.max_images
            issues.append(
                CompatibilityIssue(
                    category="media",
                    severity="warning",
                    message=f"Only {limits.max_images} of {len(post.media_attachments)} media items can be transferred",
                    details={
                        "count": len(post.media_attachments),
                        "max": limits.max_images,
                        "will_skip": extra,
                    },
                )
            )

    # Check link embed
    if post.link_embed:
        if limits.supports_link_embed:
            report.can_transfer_link_embed = True
            if target_platform == "mastodon" and post.link_embed.url not in post.text:
                issues.append(
                    CompatibilityIssue(
                        category="embed",
                        severity="warning",
                        message="Mastodon generates cards from URLs in text. URL may need to be included.",
                        details={"url": post.link_embed.url},
                    )
                )

    report.issues = issues

    # Determine final level (if not already set to REQUIRES_CHOICE)
    if report.level != CompatibilityLevel.REQUIRES_CHOICE:
        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"]

        if errors:
            report.level = CompatibilityLevel.TEXT_ONLY
        elif warnings:
            report.level = CompatibilityLevel.PARTIAL
        else:
            report.level = CompatibilityLevel.FULL

    return report


def generate_recommendations(report: CompatibilityReport) -> list[str]:
    """Generate human-readable recommendations from compatibility report."""
    recommendations = []

    if report.level == CompatibilityLevel.REQUIRES_CHOICE:
        recommendations.append(
            "This post has both media and a link embed. "
            "Set transfer_media=False to transfer link embed, or "
            "transfer_link_embed=False to transfer media."
        )

    if report.text_needs_truncation:
        recommendations.append(
            f"Text needs to be shortened. Use modify_text parameter with suggested text or your own version."
        )

    if report.can_transfer_media and report.media_transfer_count > 0:
        msg = f"{report.media_transfer_count} media item(s) can be transferred."
        if report.media_skipped_count > 0:
            msg += f" {report.media_skipped_count} will be skipped due to format."
        recommendations.append(msg)
    elif report.has_both_media_and_embed:
        pass  # Already handled above
    elif any(i.category == "media" for i in report.issues):
        recommendations.append("Some media cannot be transferred. Post will be text-only.")

    if report.can_transfer_link_embed and not report.has_both_media_and_embed:
        recommendations.append("Link embed/card will be transferred.")

    return recommendations
