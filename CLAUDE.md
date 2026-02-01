# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Ripplecast** is a Model Context Protocol server that enables cross-posting between Mastodon and Bluesky. Users interact with it through Claude Desktop to:
- View their posts across platforms
- Find posts that haven't been cross-posted
- Cross-post content with confirmation

*Like ripples spreading across water, your posts spread across platforms.*

## Quick Reference

**Always use the virtual environment in `.venv`** when running Python scripts, tests, or tools.

### Running the Server

```bash
.venv/bin/python -m ripplecast.server

# With MCP Inspector
npx @modelcontextprotocol/inspector .venv/bin/python -m ripplecast.server
```

### Running Tests

```bash
.venv/bin/pytest tests/

# Specific test file
.venv/bin/pytest tests/test_matching.py -v

# With coverage
.venv/bin/pytest tests/ --cov=ripplecast
```

### Code Formatting

```bash
.venv/bin/isort src/ripplecast/
.venv/bin/black src/ripplecast/
.venv/bin/mypy src/ripplecast/
```

## Architecture Decisions

### Why FastMCP?

We use `FastMCP` from the MCP Python SDK because it:
- Handles protocol compliance automatically
- Provides clean decorator-based tool registration
- Manages connection lifecycle

### Why Plugin Architecture?

The platform plugin system (`platforms/base.py`) allows:
- Easy addition of new platforms (Twitter, Threads, etc.)
- Platform-specific logic encapsulation
- Testability through interface contracts

### Why JSON File for Sync Store?

The sync history uses a simple JSON file because:
- No external database dependencies
- Easy to inspect and debug
- Sufficient for personal use scale
- Can be migrated to SQLite later if needed

## Key Files

| File | Purpose |
|------|---------|
| `server.py` | MCP server entry point, tool definitions |
| `platform_manager.py` | Registers and routes to platform plugins |
| `platforms/base.py` | Abstract base class all platforms implement |
| `platforms/mastodon.py` | Mastodon API integration |
| `platforms/bluesky.py` | Bluesky AT Protocol integration |
| `matching.py` | LLM-based post matching via sampling |
| `models.py` | Shared data classes (Post, LinkEmbed, etc.) |
| `media.py` | Async media download utilities for cross-posting |
| `compatibility.py` | Cross-post compatibility analysis between platforms |

## Common Tasks

### Adding a New MCP Tool

1. Add the tool function in `server.py`:
```python
@mcp.tool()
async def my_new_tool(param: str) -> dict:
    """Tool description shown to Claude."""
    # Implementation
    return {"result": "..."}
```

2. The tool is automatically registered and available.

### Adding a New Platform

1. Create `platforms/newplatform.py`
2. Implement all abstract methods from `PlatformPlugin`
3. Register in `platform_manager.py`
4. Add environment variables to `.env.example`
5. Add tests in `tests/test_newplatform.py`

### Modifying Post Matching Logic

The matching uses MCP **sampling** to ask Claude to compare posts. See `matching.py`:
- `match_posts_with_llm()`: Formats posts and sends to Claude via sampling
- The prompt asks Claude to return JSON with match results
- Adjust the prompt if matching behavior needs tuning

## Testing Notes

### Mocking External APIs

Use `unittest.mock` or `pytest-mock` to avoid real API calls:

```python
@pytest.fixture
def mock_mastodon(mocker):
    mock = mocker.patch('ripplecast.platforms.mastodon.Mastodon')
    mock.return_value.account_statuses.return_value = [...]
    return mock
```

### Test Data

Keep test fixtures in `tests/fixtures/` as JSON files:
- `mastodon_posts.json`
- `bluesky_posts.json`
- `sync_records.json`

## Error Handling Patterns

Always return structured errors from tools:

```python
if not platform.connected:
    return {
        "success": False,
        "error": "platform_not_connected",
        "message": f"Not connected to {platform_name}",
        "details": {"platform": platform_name}
    }
```

## Environment Variables

Required for development:
- `MASTODON_INSTANCE_URL`
- `MASTODON_ACCESS_TOKEN`
- `BLUESKY_HANDLE`
- `BLUESKY_APP_PASSWORD`

Copy `.env.example` to `.env` and fill in your test credentials.

## Dependencies

Key libraries and their purposes:
- `mcp`: MCP SDK for server implementation
- `Mastodon.py`: Mastodon API client
- `atproto`: Bluesky AT Protocol client
- `python-dotenv`: Environment variable loading

## Gotchas

### Mastodon.py

- Instance URL must include `https://`
- Access token scopes matter - need read AND write for full functionality
- Rate limits vary by instance

### atproto (Bluesky)

- Use App Password, not account password
- Handle format is `username.bsky.social` (no @)
- Posts have 300 char limit (shorter than Mastodon)
- **Facets for rich text**: Bluesky truncates URLs for display but stores full URLs in `record.facets`. Use `_expand_facets_in_text()` to reconstruct full URLs for cross-posting to Mastodon (which needs full URLs to generate link cards)

### MCP

- Tools must return JSON-serializable data
- Async functions are supported and preferred
- Tool descriptions become the LLM's understanding of what the tool does
- **Sampling**: Use `ctx.session.create_message()` to ask Claude for help
  - Requires `ctx: Context[ServerSession, None]` parameter in tool
  - Returns a result with `.content.text` containing Claude's response
  - Parse JSON responses carefully with error handling

## Spec Reference

See Github issue #1 of the current repo for complete details on:
- Data models
- API contracts
- Tool specifications
- Error codes
