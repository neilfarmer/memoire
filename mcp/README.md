# Memoire MCP Server

MCP (Model Context Protocol) server that exposes the Memoire API as tools for AI assistants.

## Prerequisites

- Python 3.10+
- A deployed Memoire stack
- A Personal Access Token (PAT) from the Memoire app (Settings > Tokens)

## Installation

```bash
cd mcp
pip install -e .
```

Or install directly:

```bash
pip install /path/to/memoire/mcp
```

## Configuration

The server reads two environment variables:

| Variable | Description |
|---|---|
| `MEMOIRE_API_URL` | Base URL of the deployed API (e.g. `https://api.memoire.example.com`) |
| `MEMOIRE_PAT` | Personal Access Token (starts with `pat_`) |

## Usage with Claude Code

Add to your Claude Code MCP config. Use `~/.claude/settings.json` (user-level) to
keep `MEMOIRE_PAT` out of version control. If you use a project-level
`.claude/settings.json`, make sure it is in `.gitignore` before adding secrets.

```json
{
  "mcpServers": {
    "memoire": {
      "command": "memoire-mcp",
      "env": {
        "MEMOIRE_API_URL": "https://your-api-url.example.com",
        "MEMOIRE_PAT": "pat_your_token_here"
      }
    }
  }
}
```

Or run via `uv` without installing:

```json
{
  "mcpServers": {
    "memoire": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/memoire/mcp", "memoire-mcp"],
      "env": {
        "MEMOIRE_API_URL": "https://your-api-url.example.com",
        "MEMOIRE_PAT": "pat_your_token_here"
      }
    }
  }
}
```

## Available Tools

The server exposes tools for every Memoire feature:

**Tasks** -- list, get, create, update, delete tasks and task folders
**Notes** -- list, get, create, update, delete notes and note folders (with search)
**Journal** -- list, get, create/update, delete journal entries (with search)
**Goals** -- list, get, create, update, delete goals
**Habits** -- list, create, update, delete habits; toggle daily completion
**Health** -- list, get, create/update, delete exercise logs
**Nutrition** -- list, get, create/update, delete nutrition logs
**Diagrams** -- list, get, create, update, delete Excalidraw diagrams
**Bookmarks** -- list, get, create, update, delete bookmarks (with tag filter and search)
**Favorites** -- list, create, update tags, delete saved articles
**Feeds** -- list, add, delete feeds; list articles, get article text, mark as read
**Finances** -- CRUD for debts, income, and fixed expenses; financial summary
**Settings** -- get and update user settings; test notifications
**Assistant** -- chat with Pip, manage conversation history, memory, and profile
**Home/Admin** -- AWS cost breakdown, admin statistics
**Export** -- download all data as ZIP
**Tokens** -- list, create, revoke personal access tokens

## Development

Run the server directly for testing:

```bash
MEMOIRE_API_URL=https://... MEMOIRE_PAT=pat_... python -m memoire_mcp.server
```

Inspect available tools:

```bash
MEMOIRE_API_URL=https://... MEMOIRE_PAT=pat_... mcp dev memoire_mcp/server.py
```
