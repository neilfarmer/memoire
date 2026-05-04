# memoire TUI

Terminal client for memoire, distributed as a single static binary.

Built with [Bubble Tea](https://github.com/charmbracelet/bubbletea), Lipgloss, Bubbles, and Huh. No CGO; `go build` produces a static binary on every supported platform.

## Install

From a checkout of this repo:

```bash
make tui-build         # builds bin/memoire
./bin/memoire          # run
```

Or directly with Go:

```bash
go run ./tui/cmd/memoire
```

## First-run setup

The first launch prompts for the API URL and Personal Access Token, then writes them to `~/.config/memoire-tui/config.toml` with `0600` permissions (or `$XDG_CONFIG_HOME/memoire-tui/config.toml` if set).

You can also pre-supply them via environment variables, which override the config file:

```bash
export MEMOIRE_API_URL="https://api.memoire.example.com"
export MEMOIRE_PAT="pat_..."
memoire
```

Generate a Personal Access Token in the web UI under **Settings → API Tokens**. PATs cannot create or revoke other PATs (the Tokens screen displays a banner and disables mutating actions when the session is PAT-authenticated).

## Flags

| Flag | Purpose |
|------|---------|
| `-h, --help` | show help and exit |
| `-v, --version` | print version and commit |
| `--config <path>` | use an alternate config file |
| `--no-color` | disable color output |

## Environment

| Variable | Effect |
|----------|--------|
| `MEMOIRE_API_URL` | API base URL (overrides config) |
| `MEMOIRE_PAT` | Personal Access Token (overrides config) |
| `EDITOR` | editor used for note / journal bodies (default `vi`) |
| `BROWSER` | command to open URLs (defaults to `open` on darwin, `xdg-open` on linux, `rundll32` on windows) |
| `XDG_CONFIG_HOME` | overrides config directory |
| `NO_COLOR` | set to disable color (mirrors `--no-color`) |

## Keys

Global:

| Key | Action |
|-----|--------|
| `?` | toggle help overlay |
| `ctrl+q` | quit |
| `1`–`9` | jump to the first 9 sidebar entries |
| `g <letter>` | leader nav (`g t` = tasks, `g n` = notes, …) |
| `ctrl+r` | refresh current screen |

Per-screen keys are listed in the help overlay and the bottom status bar.

## Screens

| Screen | Notes |
|--------|-------|
| Dashboard | Today's tasks / habits / latest note summary |
| Tasks | Filter / sort / group + create-edit-delete + auto-schedule + 7-day agenda |
| Notes | Folder tree + markdown rendering. `ctrl+e` in the body editor opens `$EDITOR`. |
| Journal | Month calendar with markers; one entry per day; mood + tags |
| Habits | 30-day ASCII history per habit; `space` toggles today |
| Goals | Status filter + form |
| Health | Date picker, totals, foods, exercises, 7-day summary |
| Nutrition | Date picker, meal log, totals row |
| Finances | Tabs: debts / income / expenses + summary header |
| Feeds | Two-pane (feeds / articles); inline article reader; favorite + mark read |
| Bookmarks | Search + tag filter |
| Favorites | Tag filter + remove |
| Settings | Account / Appearance / Notifications / Editor + export + test-notification |
| Tokens | List / create. Disabled and labeled when session is PAT-authenticated. |
| Assistant | Multi-turn chat with model picker + conversations. Spinner-then-render (no streaming). |
| Admin | Costs + DynamoDB / S3 stats. Sidebar entry stays available; the screen shows "(unavailable)" for non-admin users. |

Diagrams (canvas-based) is intentionally not in the TUI.

## Running tests

```bash
make tui-test          # go test ./tui/...
make tui-lint          # go vet
```

## Layout

```
tui/
  cmd/memoire/main.go             # entry point
  internal/
    api/                          # HTTP client per feature
    config/                       # TOML + env loader, first-run prompt
    styles/                       # adaptive color palette + shared lipgloss styles
    ui/
      app.go                      # root model + screen routing
      keys.go                     # global key bindings
      messages.go                 # tea.Msg types
      factories.go                # screen factory map
      components/                 # sidebar, statusbar, header, confirm, help, markdown, editor, opener, datepicker, asciichart
      screens/                    # one Model per feature
```
