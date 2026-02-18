"""LLM-based post matching via MCP sampling."""

import json
import logging
from typing import TYPE_CHECKING, Any

from mcp.server.session import ServerSession
from mcp.types import SamplingMessage, TextContent

from ripplecast.models import Post, PostMatch

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context

logger = logging.getLogger(__name__)


async def match_posts_with_llm(
    posts_a: list[Post],
    posts_b: list[Post],
    ctx: "Context[ServerSession, Any]",
    platform_a: str = "Platform A",
    platform_b: str = "Platform B",
) -> list[PostMatch]:
    """
    Use LLM sampling to match posts across platforms.

    Args:
        posts_a: Posts from the first platform
        posts_b: Posts from the second platform
        ctx: MCP context for sampling
        platform_a: Display name for first platform
        platform_b: Display name for second platform

    Returns:
        List of PostMatch objects for matched posts
    """
    if not posts_a or not posts_b:
        return []

    # Format posts for comparison (limit text to avoid token explosion)
    posts_a_formatted = "\n".join(
        [
            f"[A{i}] ({p.created_at.strftime('%Y-%m-%d %H:%M')}): {p.text[:200]}"
            for i, p in enumerate(posts_a)
        ]
    )

    posts_b_formatted = "\n".join(
        [
            f"[B{i}] ({p.created_at.strftime('%Y-%m-%d %H:%M')}): {p.text[:200]}"
            for i, p in enumerate(posts_b)
        ]
    )

    prompt = f"""Compare these two lists of social media posts and identify which posts are the same content (cross-posted).

Posts from {platform_a}:
{posts_a_formatted}

Posts from {platform_b}:
{posts_b_formatted}

For each match found, respond with a JSON array of objects:
[
  {{"a_index": 0, "b_index": 2, "confidence": 0.95, "reason": "identical text"}},
  ...
]

Only include matches with confidence >= 0.7. Consider:
- Exact or near-exact text matches
- Same content with minor edits (typos, length adjustments)
- Same links or media references

If no matches found, return an empty array: []

Respond ONLY with the JSON array, no other text."""

    try:
        result = await ctx.session.create_message(
            messages=[
                SamplingMessage(
                    role="user",
                    content=TextContent(type="text", text=prompt),
                )
            ],
            max_tokens=1000,
        )

        # Parse the JSON response
        if hasattr(result, "content") and hasattr(result.content, "text"):
            response_text = result.content.text.strip()

            # Handle potential markdown code blocks
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1])

            matches_data = json.loads(response_text)

            matches = []
            for m in matches_data:
                a_idx = m.get("a_index")
                b_idx = m.get("b_index")
                confidence = m.get("confidence", 0.0)
                reason = m.get("reason", "")

                if a_idx is not None and b_idx is not None:
                    if 0 <= a_idx < len(posts_a) and 0 <= b_idx < len(posts_b):
                        matches.append(
                            PostMatch(
                                post_a_id=posts_a[a_idx].id,
                                post_b_id=posts_b[b_idx].id,
                                confidence=confidence,
                                reason=reason,
                            )
                        )

            return matches

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM response as JSON: {e}")
    except Exception as e:
        logger.error(f"Error during post matching: {e}")

    return []


def find_unmatched_posts(
    posts: list[Post],
    matches: list[PostMatch],
    platform: str,
) -> list[Post]:
    """
    Find posts that don't have any matches.

    Args:
        posts: List of posts from a platform
        matches: List of matches found
        platform: Which platform these posts are from ("a" or "b")

    Returns:
        Posts that have no matches
    """
    # Get all matched post IDs for this platform
    if platform == "a":
        matched_ids = {m.post_a_id for m in matches}
    else:
        matched_ids = {m.post_b_id for m in matches}

    # Return posts that aren't matched
    return [p for p in posts if p.id not in matched_ids]


def build_sync_summary(
    mastodon_posts: list[Post],
    bluesky_posts: list[Post],
    matches: list[PostMatch],
) -> dict[str, Any]:
    """
    Build a summary of sync status between platforms.

    Returns a dict with:
    - mastodon_only: Posts only on Mastodon
    - bluesky_only: Posts only on Bluesky
    - synced: Posts that exist on both
    - summary: Count summary
    """
    mastodon_only = find_unmatched_posts(mastodon_posts, matches, "a")
    bluesky_only = find_unmatched_posts(bluesky_posts, matches, "b")

    return {
        "mastodon_only": [p.to_dict() for p in mastodon_only],
        "bluesky_only": [p.to_dict() for p in bluesky_only],
        "synced": [
            {
                "mastodon_id": m.post_a_id,
                "bluesky_id": m.post_b_id,
                "confidence": m.confidence,
                "reason": m.reason,
            }
            for m in matches
        ],
        "summary": {
            "mastodon_only_count": len(mastodon_only),
            "bluesky_only_count": len(bluesky_only),
            "synced_count": len(matches),
            "total_mastodon": len(mastodon_posts),
            "total_bluesky": len(bluesky_posts),
        },
    }
