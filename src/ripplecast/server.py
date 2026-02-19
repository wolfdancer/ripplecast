"""Ripplecast MCP Server - Cross-posting between Mastodon and Bluesky."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from ripplecast.compatibility import (
    CompatibilityLevel,
    analyze_cross_post_compatibility,
    generate_recommendations,
)
from ripplecast.matching import build_sync_summary, match_posts_with_llm
from ripplecast.media import download_media, download_thumbnail
from ripplecast.models import (
    AccountNotFoundError,
    AuthenticationError,
    LinkEmbed,
    PostNotFoundError,
    PostTooLongError,
)
from ripplecast.platform_manager import get_platform_manager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the MCP server
mcp = FastMCP("Ripplecast")


@mcp.tool()
async def list_accounts() -> dict[str, Any]:
    """
    List all configured social media accounts and their connection status.

    Returns account info including name, platform type, display name,
    connection status, and authenticated username.
    """
    manager = await get_platform_manager()
    statuses = await manager.get_account_status()

    return {"accounts": statuses}


@mcp.tool()
async def get_posts(
    account: str,
    limit: int = 20,
    exclude_replies: bool = True,
    exclude_reposts: bool = True,
) -> dict[str, Any]:
    """
    Get recent posts from an account.

    Args:
        account: Account name (e.g., "personal-bluesky", "work-mastodon")
        limit: Maximum posts to fetch (default 20, max 100)
        exclude_replies: Skip reply posts (default True)
        exclude_reposts: Skip reposts/boosts (default True)

    Returns:
        List of posts with id, text, created_at, url, and media info
    """
    manager = await get_platform_manager()

    try:
        plugin = manager.get_account(account)
        platform = manager.get_account_platform(account)

        if not plugin.connected:
            return {
                "success": False,
                "error": "account_not_connected",
                "message": f"Not connected to account '{account}'",
            }

        user = await plugin.get_current_user()
        posts = await manager.get_posts(
            account=account,
            limit=min(limit, 100),
            exclude_replies=exclude_replies,
            exclude_reposts=exclude_reposts,
        )

        return {
            "success": True,
            "account": account,
            "platform": platform,
            "username": user.get("username"),
            "post_count": len(posts),
            "posts": [p.to_dict() for p in posts],
        }

    except AccountNotFoundError as e:
        return {
            "success": False,
            "error": "account_not_found",
            "message": str(e),
        }
    except AuthenticationError as e:
        return {
            "success": False,
            "error": "authentication_error",
            "message": str(e),
        }
    except Exception as e:
        logger.error(f"Error fetching posts from {account}: {e}")
        return {
            "success": False,
            "error": "fetch_error",
            "message": str(e),
        }


@mcp.tool()
async def find_unsynced_posts(
    source_account: str | None = None,
    days_back: int = 7,
    ctx: Context[ServerSession, Any] | None = None,
) -> dict[str, Any]:
    """
    Find posts that exist on one account but not on others.

    Uses Claude (via MCP sampling) to intelligently match posts,
    handling variations in text, URLs, and formatting.

    Args:
        source_account: Only check posts from this account (optional).
                       If not specified, checks all accounts.
        days_back: How many days of posts to analyze (default 7)

    Returns:
        Posts grouped by account that are missing from other accounts,
        including any partial matches found
    """
    if ctx is None:
        return {
            "success": False,
            "error": "context_required",
            "message": "This tool requires sampling context",
        }

    manager = await get_platform_manager()

    try:
        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back)

        # Fetch posts from all accounts
        all_posts = await manager.get_all_posts(
            limit=50,  # Reasonable batch for comparison
            exclude_replies=True,
            exclude_reposts=True,
        )

        # Separate posts by platform type for matching
        mastodon_posts = []
        bluesky_posts = []
        account_map: dict[str, str] = {}  # post_id -> account_name
        plugin_map = {}  # post_id -> plugin (for Signal 2 checks)

        for account_name, posts in all_posts.items():
            platform = manager.get_account_platform(account_name)
            plugin = manager.get_account(account_name)
            for post in posts:
                if post.created_at >= start_date:
                    if platform == "mastodon":
                        mastodon_posts.append(post)
                    elif platform == "bluesky":
                        bluesky_posts.append(post)
                    account_map[post.id] = account_name
                    plugin_map[post.id] = plugin

        if not mastodon_posts and not bluesky_posts:
            return {
                "success": True,
                "message": f"No posts found in the last {days_back} days",
                "unsynced": {},
                "summary": {
                    "total_posts": 0,
                    "unsynced_count": 0,
                    "synced_count": 0,
                },
            }

        # Use LLM to match posts between platforms
        matches = await match_posts_with_llm(
            mastodon_posts,
            bluesky_posts,
            ctx,
            platform_a="Mastodon",
            platform_b="Bluesky",
        )

        # Build sync summary
        summary = build_sync_summary(mastodon_posts, bluesky_posts, matches)

        # Signal 2: remove posts created via ripplecast from the unsynced lists
        post_objects = {p.id: p for p in mastodon_posts + bluesky_posts}
        ripplecast_synced = []

        def _filter_via_ripplecast(post_dicts: list) -> list:
            remaining = []
            for post_dict in post_dicts:
                post_id = post_dict.get("id", "")
                post = post_objects.get(post_id)
                plugin = plugin_map.get(post_id)
                if post and plugin and plugin.is_posted_via_ripplecast(post):
                    ripplecast_synced.append(
                        {"post_id": post_id, "platform": post_dict.get("platform"), "match_type": "posted_via_ripplecast"}
                    )
                else:
                    remaining.append(post_dict)
            return remaining

        summary["mastodon_only"] = _filter_via_ripplecast(summary["mastodon_only"])
        summary["bluesky_only"] = _filter_via_ripplecast(summary["bluesky_only"])
        summary["summary"]["mastodon_only_count"] = len(summary["mastodon_only"])
        summary["summary"]["bluesky_only_count"] = len(summary["bluesky_only"])
        summary["summary"]["synced_count"] += len(ripplecast_synced)

        # Reconcile: a Bluesky post tagged as ripplecast means a Mastodon post was
        # its source. That Mastodon original must not appear in mastodon_only.
        # The LLM may have missed the match, so we do text-based reconciliation here.
        ripplecast_bsky_ids = {
            e["post_id"] for e in ripplecast_synced if e.get("platform") == "bluesky"
        }
        if ripplecast_bsky_ids:
            mastodon_ids_to_remove: set[str] = set()
            for bsky_id in ripplecast_bsky_ids:
                bsky_post = post_objects.get(bsky_id)
                if bsky_post is None:
                    continue
                bsky_text = bsky_post.text.strip()
                for mastodon_dict in summary["mastodon_only"]:
                    masto_id = mastodon_dict.get("id", "")
                    masto_post = post_objects.get(masto_id)
                    if masto_post is None:
                        continue
                    masto_text = masto_post.text.strip()
                    # Match exact text, or Bluesky was truncated with "..." suffix
                    if masto_text == bsky_text or (
                        bsky_text.endswith("...") and masto_text.startswith(bsky_text[:-3])
                    ):
                        mastodon_ids_to_remove.add(masto_id)
                        break
            if mastodon_ids_to_remove:
                summary["mastodon_only"] = [
                    p for p in summary["mastodon_only"]
                    if p.get("id") not in mastodon_ids_to_remove
                ]
                summary["summary"]["mastodon_only_count"] = len(summary["mastodon_only"])

        # Filter by source account if specified
        if source_account:
            source_platform = manager.get_account_platform(source_account)
            if source_platform == "mastodon":
                summary["bluesky_only"] = []
                summary["summary"]["bluesky_only_count"] = 0
            elif source_platform == "bluesky":
                summary["mastodon_only"] = []
                summary["summary"]["mastodon_only_count"] = 0

        # Annotate posts with their account names
        for post_dict in summary.get("mastodon_only", []):
            post_dict["account"] = account_map.get(post_dict.get("id", ""), "unknown")
        for post_dict in summary.get("bluesky_only", []):
            post_dict["account"] = account_map.get(post_dict.get("id", ""), "unknown")

        return {
            "success": True,
            "analysis_period": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
            "unsynced": {
                "mastodon_only": summary["mastodon_only"],
                "bluesky_only": summary["bluesky_only"],
            },
            "already_synced": summary["synced"],
            "already_synced_via_ripplecast": ripplecast_synced,
            "summary": summary["summary"],
        }

    except Exception as e:
        logger.error(f"Error finding unsynced posts: {e}")
        return {
            "success": False,
            "error": "sync_check_error",
            "message": str(e),
        }


@mcp.tool()
async def cross_post(
    source_account: str,
    post_id: str,
    target_account: str,
    modify_text: str | None = None,
    transfer_media: bool = True,
    transfer_link_embed: bool = True,
) -> dict[str, Any]:
    """
    Cross-post a post from one account to another.

    Args:
        source_account: Account where the original post exists (e.g., "personal-mastodon")
        post_id: ID of the post to cross-post
        target_account: Account to post to (e.g., "personal-bluesky")
        modify_text: Optional modified text (e.g., to fit character limit).
                    If not provided, uses original text.
        transfer_media: Whether to transfer media attachments (default True)
        transfer_link_embed: Whether to transfer link embeds (default True)

    Returns:
        Result including new post ID, URL, and what content was transferred.
        If post has both media and link embed, returns error requiring choice.
    """
    manager = await get_platform_manager()

    try:
        # Get the source and target plugins
        source = manager.get_account(source_account)
        target = manager.get_account(target_account)
        target_platform = manager.get_account_platform(target_account)

        if not source.connected:
            return {
                "success": False,
                "error": "source_not_connected",
                "message": f"Not connected to account '{source_account}'",
            }

        if not target.connected:
            return {
                "success": False,
                "error": "target_not_connected",
                "message": f"Not connected to account '{target_account}'",
            }

        # Fetch the original post
        original_post = await source.get_post_by_id(post_id)
        if not original_post:
            return {
                "success": False,
                "error": "post_not_found",
                "message": f"Post {post_id} not found on account '{source_account}'",
            }

        # Analyze compatibility
        report = analyze_cross_post_compatibility(
            original_post, target_platform, target.max_post_length
        )

        # Check for media + embed conflict
        if report.has_both_media_and_embed and transfer_media and transfer_link_embed:
            return {
                "success": False,
                "error": "content_choice_required",
                "message": "Post has both media and link embed. Bluesky only supports one.",
                "suggestion": "Set transfer_media=False to transfer link embed, or transfer_link_embed=False to transfer media.",
                "compatibility": report.to_dict(),
            }

        # Use modified text or original (or suggested truncation)
        text_to_post = modify_text if modify_text else original_post.text
        if not modify_text and report.text_needs_truncation and report.suggested_text:
            text_to_post = report.suggested_text

        # Validate text length
        is_valid, error = target.validate_post_content(text_to_post)
        if not is_valid:
            max_len = target.max_post_length
            suggested = (
                text_to_post[: max_len - 3] + "..." if len(text_to_post) > max_len else text_to_post
            )

            return {
                "success": False,
                "error": "text_too_long",
                "message": f"Post is {len(text_to_post)} characters but {target_platform} allows max {max_len}",
                "original_text": text_to_post,
                "suggested_truncation": suggested,
                "suggestion": "Use modify_text parameter with shortened version",
            }

        # Download and prepare media
        downloaded_media = []
        if transfer_media and original_post.media_attachments and report.can_transfer_media:
            for attachment in original_post.media_attachments[:4]:
                media = await download_media(attachment)
                if media:
                    downloaded_media.append(media)

        # Prepare link embed
        link_embed = None
        if transfer_link_embed and original_post.link_embed and report.can_transfer_link_embed:
            # Don't transfer link embed if we're transferring media (Bluesky limitation)
            if not downloaded_media or target_platform == "mastodon":
                link_embed = original_post.link_embed
                # Download thumbnail if available
                if link_embed.thumbnail_url:
                    thumb_data = await download_thumbnail(link_embed.thumbnail_url)
                    if thumb_data:
                        link_embed = LinkEmbed(
                            url=link_embed.url,
                            title=link_embed.title,
                            description=link_embed.description,
                            thumbnail_url=link_embed.thumbnail_url,
                            thumbnail_data=thumb_data,
                        )

        # Create the post on target account
        new_post = await target.create_post(
            text=text_to_post,
            language=original_post.language,
            downloaded_media=downloaded_media if downloaded_media else None,
            link_embed=link_embed,
        )

        return {
            "success": True,
            "source": {
                "account": source_account,
                "post_id": post_id,
                "url": original_post.url,
            },
            "target": {
                "account": target_account,
                "platform": target_platform,
                "post_id": new_post.id,
                "url": new_post.url,
            },
            "transferred": {
                "text": True,
                "text_modified": modify_text is not None or report.text_needs_truncation,
                "media_count": len(downloaded_media),
                "link_embed": link_embed is not None,
            },
            "text_used": text_to_post,
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }

    except PostNotFoundError as e:
        return {
            "success": False,
            "error": "post_not_found",
            "message": str(e),
        }
    except PostTooLongError as e:
        return {
            "success": False,
            "error": "text_too_long",
            "message": str(e),
            "limit": e.limit,
            "length": e.length,
        }
    except AccountNotFoundError as e:
        return {
            "success": False,
            "error": "account_not_found",
            "message": str(e),
        }
    except Exception as e:
        logger.error(f"Error cross-posting: {e}")
        return {
            "success": False,
            "error": "cross_post_error",
            "message": str(e),
        }


@mcp.tool()
async def bulk_cross_post(
    posts: list[dict[str, Any]],
    dry_run: bool = True,
    transfer_media: bool = True,
    transfer_link_embed: bool = True,
) -> dict[str, Any]:
    """
    Cross-post multiple posts at once.

    Args:
        posts: List of dicts with keys:
               - source_account: str (account name, e.g., "personal-mastodon")
               - post_id: str
               - target_account: str (account name, e.g., "personal-bluesky")
               - modify_text: str | None (optional)
        dry_run: If True, only simulate and report what would happen.
                If False, actually perform the cross-posts.
        transfer_media: Whether to transfer media attachments (default True)
        transfer_link_embed: Whether to transfer link embeds (default True)

    Returns:
        Results for each post (success/failure/skipped) with compatibility info

    Note:
        ALWAYS run with dry_run=True first and show user the plan.
        Only run with dry_run=False after explicit user confirmation.
    """
    results: list[dict[str, Any]] = []

    for i, post_spec in enumerate(posts):
        source_account = post_spec.get("source_account")
        post_id = post_spec.get("post_id")
        target_account = post_spec.get("target_account")
        modify_text = post_spec.get("modify_text")

        if not all([source_account, post_id, target_account]):
            results.append(
                {
                    "index": i,
                    "status": "skipped",
                    "reason": "Missing required fields",
                }
            )
            continue

        # Type narrowing for mypy - we've verified these are not None
        assert isinstance(source_account, str)
        assert isinstance(post_id, str)
        assert isinstance(target_account, str)

        if dry_run:
            # Just validate and report what would happen
            manager = await get_platform_manager()
            try:
                source = manager.get_account(source_account)
                target = manager.get_account(target_account)
                target_platform = manager.get_account_platform(target_account)

                original = await source.get_post_by_id(post_id)
                if not original:
                    results.append(
                        {
                            "index": i,
                            "status": "would_fail",
                            "reason": f"Post {post_id} not found",
                        }
                    )
                    continue

                # Analyze compatibility
                report = analyze_cross_post_compatibility(
                    original, target_platform, target.max_post_length
                )

                text = modify_text or original.text
                is_valid, error = target.validate_post_content(text)

                # Check for conflicts
                status = "would_succeed"
                reason = error
                if not is_valid:
                    status = "would_fail"
                elif report.level == CompatibilityLevel.REQUIRES_CHOICE:
                    if transfer_media and transfer_link_embed:
                        status = "would_fail"
                        reason = "Has both media and embed - set transfer_media or transfer_link_embed to False"

                results.append(
                    {
                        "index": i,
                        "status": status,
                        "source_account": source_account,
                        "target_account": target_account,
                        "target_platform": target_platform,
                        "text_preview": text[:100] + "..." if len(text) > 100 else text,
                        "text_length": len(text),
                        "media_count": len(original.media_attachments),
                        "has_link_embed": original.link_embed is not None,
                        "compatibility": report.to_dict(),
                        "reason": reason,
                    }
                )

            except Exception as e:
                results.append(
                    {
                        "index": i,
                        "status": "would_fail",
                        "reason": str(e),
                    }
                )
        else:
            # Actually perform the cross-post
            result = await cross_post(
                source_account=source_account,
                post_id=post_id,
                target_account=target_account,
                modify_text=modify_text,
                transfer_media=transfer_media,
                transfer_link_embed=transfer_link_embed,
            )

            results.append(
                {
                    "index": i,
                    "status": "success" if result.get("success") else "failed",
                    "result": result,
                }
            )

    success_count = sum(1 for r in results if r["status"] in ("success", "would_succeed"))
    fail_count = sum(1 for r in results if r["status"] in ("failed", "would_fail"))

    return {
        "dry_run": dry_run,
        "total": len(posts),
        "success_count": success_count,
        "fail_count": fail_count,
        "results": results,
        "message": (
            "This is a dry run - no posts were created"
            if dry_run
            else f"Completed: {success_count} succeeded, {fail_count} failed"
        ),
    }


@mcp.tool()
async def analyze_post_compatibility(
    source_account: str,
    post_id: str,
    target_account: str,
) -> dict[str, Any]:
    """
    Analyze whether a post can be cross-posted and what content can be transferred.

    Use this before cross_post to understand what will happen.

    Args:
        source_account: Account where the post exists (e.g., "personal-mastodon")
        post_id: ID of the post to analyze
        target_account: Account to potentially cross-post to (e.g., "personal-bluesky")

    Returns:
        Detailed compatibility report including:
        - Overall compatibility level (full, partial, text_only, requires_choice)
        - What can/cannot be transferred
        - Specific issues and warnings
        - Recommendations for how to proceed
    """
    manager = await get_platform_manager()

    try:
        source = manager.get_account(source_account)
        target = manager.get_account(target_account)
        target_platform = manager.get_account_platform(target_account)

        if not source.connected:
            return {
                "success": False,
                "error": "source_not_connected",
                "message": f"Not connected to account '{source_account}'",
            }

        original = await source.get_post_by_id(post_id)
        if not original:
            return {
                "success": False,
                "error": "post_not_found",
                "message": f"Post {post_id} not found on account '{source_account}'",
            }

        report = analyze_cross_post_compatibility(original, target_platform, target.max_post_length)

        recommendations = generate_recommendations(report)

        return {
            "success": True,
            "post": original.to_dict(),
            "source_account": source_account,
            "target_account": target_account,
            "target_platform": target_platform,
            "compatibility": report.to_dict(),
            "recommendations": recommendations,
        }

    except AccountNotFoundError as e:
        return {
            "success": False,
            "error": "account_not_found",
            "message": str(e),
        }
    except PostNotFoundError as e:
        return {
            "success": False,
            "error": "post_not_found",
            "message": str(e),
        }
    except Exception as e:
        logger.error(f"Error analyzing compatibility: {e}")
        return {
            "success": False,
            "error": "analysis_error",
            "message": str(e),
        }



@mcp.tool()
async def get_sync_status(
    account: str,
    post_id: str,
    ctx: Context[ServerSession, Any] | None = None,
) -> dict[str, Any]:
    """
    Check if a post exists on other accounts (i.e., has been synced).

    Uses content matching to find the same post across platforms.

    Args:
        account: Account where the post exists (e.g., "personal-mastodon")
        post_id: ID of the post to check

    Returns:
        Status showing which accounts have matching posts
    """
    manager = await get_platform_manager()

    try:
        source = manager.get_account(account)
        source_platform = manager.get_account_platform(account)

        if not source.connected:
            return {
                "success": False,
                "error": "account_not_connected",
                "message": f"Not connected to account '{account}'",
            }

        # Get the source post
        post = await source.get_post_by_id(post_id)
        if not post:
            return {
                "success": False,
                "error": "post_not_found",
                "message": f"Post {post_id} not found on account '{account}'",
            }

        synced_to = []
        not_synced_to = []

        # Check all other accounts
        all_accounts = manager.get_all_accounts()
        for target_name, target_plugin in all_accounts.items():
            if target_name == account:
                continue  # Skip the source account

            target_platform = manager.get_account_platform(target_name)

            if not target_plugin.connected:
                not_synced_to.append(f"{target_name} (not connected)")
                continue

            # Signal 2: check ripplecast metadata first (precise, no LLM needed)
            if source.is_posted_via_ripplecast(post):
                synced_to.append(
                    {
                        "account": target_name,
                        "platform": target_platform,
                        "match_type": "posted_via_ripplecast",
                    }
                )
                continue

            if not ctx:
                not_synced_to.append(f"{target_name} (context required for matching)")
                continue

            # Signal 1: fall back to LLM content matching
            target_posts = await manager.get_posts(
                target_name,
                limit=50,
                exclude_replies=True,
                exclude_reposts=True,
            )

            matches = await match_posts_with_llm(
                [post],
                target_posts,
                ctx,
                platform_a=source_platform.title(),
                platform_b=target_platform.title(),
            )

            if matches:
                for match in matches:
                    matched_post = next(
                        (p for p in target_posts if p.id == match.post_b_id),
                        None,
                    )
                    if matched_post:
                        synced_to.append(
                            {
                                "account": target_name,
                                "platform": target_platform,
                                "post_id": matched_post.id,
                                "url": matched_post.url,
                                "similarity": match.confidence,
                                "match_type": match.reason,
                            }
                        )
            else:
                not_synced_to.append(target_name)

        return {
            "success": True,
            "source": {
                "account": account,
                "platform": source_platform,
                "post_id": post_id,
                "text": post.text,
                "created_at": post.created_at.isoformat(),
                "url": post.url,
            },
            "synced_to": synced_to,
            "not_synced_to": not_synced_to,
        }

    except PostNotFoundError as e:
        return {
            "success": False,
            "error": "post_not_found",
            "message": str(e),
        }
    except AccountNotFoundError as e:
        return {
            "success": False,
            "error": "account_not_found",
            "message": str(e),
        }
    except Exception as e:
        logger.error(f"Error checking sync status: {e}")
        return {
            "success": False,
            "error": "sync_status_error",
            "message": str(e),
        }


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
