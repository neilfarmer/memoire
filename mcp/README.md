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

The server reads these environment variables:

| Variable | Description |
|---|---|
| `MEMOIRE_API_URL` | Base URL of the deployed API (e.g. `https://api.memoire.example.com`) |
| `MEMOIRE_PAT` | Personal Access Token (starts with `pat_`) |
| `MEMOIRE_MCP_TRANSPORT` | `stdio` (default), `streamable-http`, or `sse` |
| `MEMOIRE_MCP_HOST` | Bind host for HTTP transports (default `0.0.0.0`) |
| `MEMOIRE_MCP_PORT` | Bind port for HTTP transports (default `8000`) |
| `MEMOIRE_MCP_PATH` | Mount path for HTTP transports (default `/mcp`) |

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

## Standalone HTTP server (Docker / Kubernetes)

Run the MCP server as its own networked service so any MCP client (e.g.
an OpenClaw gateway) can connect via URL instead of spawning it as a
local stdio child:

```bash
docker build -t memoire-mcp:latest mcp
docker run --rm -p 8000:8000 \
  -e MEMOIRE_API_URL=https://api.memoire.example.com \
  -e MEMOIRE_PAT=pat_... \
  memoire-mcp:latest
```

The image's default entrypoint sets `MEMOIRE_MCP_TRANSPORT=streamable-http`
and binds `0.0.0.0:8000/mcp`. Connect any MCP client at
`http://<host>:8000/mcp`.

Example client-side config (Streamable HTTP MCP server):

```json
{
  "mcpServers": {
    "memoire": {
      "url": "https://memoire-mcp.example.com/mcp",
      "transport": "streamable-http"
    }
  }
}
```

## Available Tools

The server exposes tools for every Memoire feature. Each feature's fields mirror the underlying REST API, including optional scheduling and notification settings.

**Tasks** -- list, get, create, update, delete tasks and task folders. Supports `notifications` (reminders `before_due` of `1h`/`1d`/`3d` and `recurring` of `1h`/`1d`/`1w`).
**Notes** -- list, get, create, update, delete notes and note folders (with search). Supports inline image uploads and file attachments (presigned S3 URLs, optional `size` for quota).
**Journal** -- list, get, create/update, delete journal entries (with search).
**Goals** -- list, get, create, update, delete goals with `progress` (0-100).
**Habits** -- list, create, update, delete habits; toggle daily completion. Supports `notify_time` (HH:MM UTC) and `time_of_day` (`morning`/`afternoon`/`evening`/`anytime`).
**Health** -- list, get, create/update, delete exercise logs (sets of `reps`/`weight`, optional `duration`).
**Nutrition** -- list, get, create/update, delete nutrition logs (per-meal macros).
**Diagrams** -- list, get, create, update, delete Excalidraw diagrams.
**Bookmarks** -- list, get, create, update, delete bookmarks (with tag filter and search).
**Favorites** -- list, create, update tags, delete saved articles.
**Feeds** -- list, add, delete feeds; list articles (with cache-refresh), get article text, mark as read.
**Finances** -- CRUD for debts, income, and fixed expenses; financial summary with monthly totals.
**Settings** -- get and update user settings (`dark_mode`, `ntfy_url`, `autosave_seconds`, `timezone`, `display_name`, `pal_name`, `profile_inference_hours`, `home_finances_widget`, `chat_retention_days`); test notifications (optionally overriding URL).
**Assistant** -- chat with Pip (supports `no_history` one-shot mode and multi-thread `conversation_id`), list/create/get/rename/delete saved chat threads, manage conversation history, memory, facts, and profile; trigger AI profile analysis.
**Home/Admin** -- AWS cost breakdown, admin statistics.
**Export** -- download all data as a ZIP.
**Tokens** -- list, create, revoke personal access tokens (JWT-only on server; calls return 403 when MCP authenticates with a PAT).

## Development

Run the server directly for testing:

```bash
MEMOIRE_API_URL=https://... MEMOIRE_PAT=pat_... python -m memoire_mcp.server
```

Inspect available tools:

```bash
MEMOIRE_API_URL=https://... MEMOIRE_PAT=pat_... mcp dev memoire_mcp/server.py
```
