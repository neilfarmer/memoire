# Playwright Setup for AI Testing

Claude Code uses the Playwright MCP server to test frontend changes in a real browser after deploys.

## Prerequisites

Install the Playwright MCP server via npm:

```bash
npm install -g @playwright/mcp
```

Then install the browser binaries:

```bash
npx playwright install chromium
```

## Claude Code Configuration

Add the Playwright MCP server to your Claude Code config (`~/.claude/claude_desktop_config.json` or via `claude mcp add`):

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp"]
    }
  }
}
```

## Usage

Once configured, Claude Code can navigate to the CloudFront URL, interact with the UI, and take screenshots to verify changes after a `make deploy-auto`. The CloudFront URL is available via `terraform output frontend_url`.
