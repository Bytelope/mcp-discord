# Discord MCP Server

[![smithery badge](https://smithery.ai/badge/@hanweg/mcp-discord)](https://smithery.ai/server/@hanweg/mcp-discord)
A Model Context Protocol (MCP) server that provides Discord integration capabilities to autonomous agents running on Claude Code.

<a href="https://glama.ai/mcp/servers/wvwjgcnppa"><img width="380" height="200" src="https://glama.ai/mcp/servers/wvwjgcnppa/badge" alt="mcp-discord MCP server" /></a>

## Available Tools

### Server Information
- `list_servers`: List available servers
- `get_server_info`: Get detailed server information
- `get_channels`: List channels in a server
- `list_members`: List server members and their roles
- `get_user_info`: Get detailed information about a user

### Message Management
- `send_message`: Send a message to a channel
- `read_messages`: Read recent message history
- `add_reaction`: Add a reaction to a message
- `add_multiple_reactions`: Add multiple reactions to a message
- `remove_reaction`: Remove a reaction from a message
- `moderate_message`: Delete messages and timeout users

### Channel Management
- `create_text_channel`: Create a new text channel
- `delete_channel`: Delete an existing channel

### Role Management
- `add_role`: Add a role to a user
- `remove_role`: Remove a role from a user

## Installation

1. Set up your Discord bot:
   - Create a new application at [Discord Developer Portal](https://discord.com/developers/applications)
   - Create a bot and copy the token
   - Enable required privileged intents:
     - MESSAGE CONTENT INTENT
     - PRESENCE INTENT
     - SERVER MEMBERS INTENT
   - Invite the bot to your server using OAuth2 URL Generator

2. Clone and install the package:
```bash
# Clone the repository
git clone https://github.com/hanweg/mcp-discord.git
cd mcp-discord

# Create and activate virtual environment
uv venv
.venv\Scripts\activate # On macOS/Linux, use: source .venv/bin/activate

### If using Python 3.13+ - install audioop library: `uv pip install audioop-lts`

# Install the package
uv pip install -e .
```

3. Configure Claude Desktop (`%APPDATA%\Claude\claude_desktop_config.json` on Windows, `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):
```json
    "discord": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\PATH\\TO\\mcp-discord",
        "run",
        "mcp-discord"
      ],
      "env": {
        "DISCORD_TOKEN": "your_bot_token"
      }
    }
```

### Installing via Smithery

To install Discord Server for Claude Desktop automatically via [Smithery](https://smithery.ai/server/@hanweg/mcp-discord):

```bash
npx -y @smithery/cli install @hanweg/mcp-discord --client claude
```

## Optional: tmux push notifications

When the agent runs inside a tmux session (e.g. under `clem`), the server
can push a one-line notification to the agent's stdin every time a new
message lands in a watched channel. The agent then decides whether to
fetch full content via `read_messages`.

Set both env vars on the MCP server process:

| Variable | Purpose |
|----------|---------|
| `DISCORD_WATCH_CHANNELS` | Comma-separated list of numeric channel IDs to watch |
| `CLEM_TMUX_TARGET` | tmux session/window/pane spec (e.g. `worker:0`) |
| `DISCORD_WATCH_DEBOUNCE` | Optional, defaults to `2.0` seconds |

Notifications look like:

```
[discord] 3 new: #general(@jahwag) #tasks(@amara,@athena)
```

If either env var is missing the watcher stays disabled — existing
deployments are unaffected.

## Running tests

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/pytest
```

## License

MIT License - see LICENSE file for details.
