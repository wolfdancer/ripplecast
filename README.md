# Ripplecast

An MCP (Model Context Protocol) server that enables cross-posting between Mastodon and Bluesky. Interact with it through Claude Desktop to manage your social media presence across platforms.

*Like ripples spreading across water, your posts spread across platforms.*

## Features

- **View posts** across Mastodon and Bluesky from a single interface
- **Find unsynced posts** - identify content that exists on one platform but not the other
- **Cross-post with confirmation** - share content between platforms with full control
- **Intelligent matching** - uses Claude to detect duplicate/similar posts across platforms

## Installation

### Prerequisites

- Python 3.11 or higher
- Claude Desktop
- Mastodon account with API access
- Bluesky account with App Password

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/ripplecast.git
   cd ripplecast
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e ".[dev]"
   ```

3. Copy `config.example.yaml` to `config.yaml` and fill in your credentials:
   ```bash
   cp config.example.yaml config.yaml
   ```

4. Configure Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`):
   ```json
   {
     "mcpServers": {
       "ripplecast": {
         "command": "/path/to/ripplecast/.venv/bin/python",
         "args": ["-m", "ripplecast.server"]
       }
     }
   }
   ```

## Getting Credentials

### Mastodon Access Token

1. Go to your Mastodon instance's Settings
2. Navigate to **Development > New Application**
3. Give it a name (e.g., "Ripplecast")
4. Required scopes: `read:accounts`, `read:statuses`, `write:statuses`
5. Copy the **Access Token** after creation

### Bluesky App Password

1. Go to **Settings** in Bluesky
2. Navigate to **App Passwords**
3. Create a new app password
4. Copy the generated password (format: `xxxx-xxxx-xxxx-xxxx`)

## Usage

Once configured, restart Claude Desktop. You can then use natural language to interact:

- "What posts do I have on Mastodon that aren't on Bluesky?"
- "Show me my recent Bluesky posts"
- "Cross-post that article I shared yesterday from Mastodon to Bluesky"
- "Sync all my unsynced posts from the last week"

## Development

### Running Tests

```bash
# All tests
pytest tests/

# With coverage
pytest tests/ --cov=ripplecast

# Specific test file
pytest tests/test_matching.py -v
```

### Code Formatting

```bash
isort src/ripplecast/
black src/ripplecast/
mypy src/ripplecast/
```

### Running with MCP Inspector

For debugging:

```bash
npx @modelcontextprotocol/inspector python -m ripplecast.server
```

## Architecture

```
┌─────────────────────┐
│   Claude Desktop    │
└──────────┬──────────┘
           │ MCP Protocol (stdio)
           ▼
┌─────────────────────────────────────┐
│        Ripplecast MCP Server        │
│  ┌────────────────────────────────┐ │
│  │     Core Server (FastMCP)      │ │
│  └────────────────────────────────┘ │
│  ┌────────────────────────────────┐ │
│  │     Platform Manager           │ │
│  │  (plugin registry & routing)   │ │
│  └────────────────────────────────┘ │
│  ┌──────────┐  ┌──────────────────┐ │
│  │ Mastodon │  │     Bluesky      │ │
│  │  Plugin  │  │      Plugin      │ │
│  └──────────┘  └──────────────────┘ │
└─────────────────────────────────────┘
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `list_accounts` | List configured accounts and connection status |
| `get_posts` | Fetch recent posts from an account |
| `find_unsynced_posts` | Find posts missing from other accounts |
| `cross_post` | Cross-post a single post |
| `bulk_cross_post` | Cross-post multiple posts (with dry-run) |
| `get_sync_status` | Check if a specific post has been synced |

## Limitations (v1)

- Media attachments are not transferred during cross-posting
- Thread/reply chains are not preserved
- No scheduled posting

## License

MIT
