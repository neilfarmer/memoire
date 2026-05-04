# Memoire TUI — Architecture

## Status

Design locked. Implementation starting.

---

## Framework Decision: Bubble Tea + Lipgloss + Bubbles + Huh

**Chosen stack:**
- `github.com/charmbracelet/bubbletea` — Elm-architecture TUI framework
- `github.com/charmbracelet/lipgloss` — Style/layout primitives (borders, padding, color, flex-like arrangement)
- `github.com/charmbracelet/bubbles` — Pre-built components: `list.Model`, `viewport.Model`, `textinput.Model`, `textarea.Model`, `spinner.Model`, `table.Model`, `key.Binding`
- `github.com/charmbracelet/huh` — Form library for structured create/edit flows with validation

**Rationale:**

1. **Bubble Tea** is the dominant Go TUI framework. Its Elm `Model / Update(Msg) / View()` pattern is clean, testable, and handles async API calls via `tea.Cmd` without blocking the render loop. It has first-class multi-screen support via nested models.
2. **Lipgloss** mirrors the CSS variable system in `frontend/index.html` well — surfaces, borders, text colors, and adaptive light/dark themes map cleanly to `lipgloss.AdaptiveColor`.
3. **Bubbles** ships `list.Model` (exactly what task/note/habit lists need), `viewport.Model` (for long content like journal entries and note bodies), and `textinput` / `textarea` for in-TUI editing — these alone cover 80% of the UI primitives needed.
4. **Huh** handles multi-field create/edit forms (task due date + priority + folder, goal description + target date, etc.) in a terminal-native way with validation and keyboard navigation.
5. The combination is proven at production scale (lazygit, soft-serve, mods, pop). No other Go TUI stack (tview, tcell raw, termui) offers the same ergonomics for a multi-screen CRUD app.

---

## Project Layout

```
tui/
  cmd/
    memoire/
      main.go            # Entry: load config, init API client, run tea.Program
  internal/
    api/                 # HTTP client layer
      client.go          # Base client: PAT auth header, base URL, error parsing
      tasks.go           # Task + folder endpoints
      notes.go           # Note + folder + attachment endpoints
      habits.go          # Habit + habit_logs_v2 endpoints
      journal.go         # Journal entry endpoints
      goals.go           # Goals endpoints
      health.go          # Health log endpoints
      nutrition.go       # Nutrition log endpoints
      finances.go        # Debts + income + fixed_expenses endpoints
      feeds.go           # Feed + articles endpoints
      bookmarks.go       # Bookmark endpoints
      diagrams.go        # Diagram endpoints
      favorites.go       # Favorites endpoints
      settings.go        # Settings endpoints
      assistant.go       # Assistant chat endpoints (streaming)
      tokens.go          # PAT management (JWT-only; flag if accessed via PAT)
      export.go          # Export endpoint
    ui/
      app.go             # Root model: screen routing, sidebar state, global key handler
      screens/           # One Bubble Tea Model per feature
        dashboard.go     # Home/overview: counts, recent items
        tasks.go         # Task list + detail + create/edit
        notes.go         # Note list + editor
        habits.go        # Habit tracker + log entry
        journal.go       # Journal entry per day (date nav)
        goals.go         # Goal list + detail
        health.go        # Health log list + entry form
        nutrition.go     # Nutrition log list + entry form
        finances.go      # Debts / income / expenses tabs
        feeds.go         # Feed list + article list + reader
        bookmarks.go     # Bookmark list + detail
        diagrams.go      # Diagram list; JSON view or external open (adaptation)
        favorites.go     # Favorites list
        settings.go      # Settings key/value editor
        assistant.go     # Chat screen with streaming output
        tokens.go        # PAT list + create (JWT-only note)
      components/        # Shared widgets
        statusbar.go     # Bottom bar: screen name, mode, flash message, key hints
        confirm.go       # Delete confirmation dialog (y/n)
        help.go          # Keybinding overlay (? to toggle)
        header.go        # Top bar: app name, current section, connection status
        sidebar.go       # Left nav: section list, keyboard + mouse nav
    config/
      config.go          # Load config: env vars > config file
    styles/
      styles.go          # Lipgloss styles, adaptive color palette
  go.mod
  go.sum
  ARCHITECTURE.md        # This file
  FEATURES.md            # Feature-by-feature API + interaction map (memoire-expert)
  UX.md                  # Layout, keybindings, patterns (tui-expert)
```

---

## Auth Model

The TUI authenticates exclusively with a Personal Access Token (PAT).

**Resolution order (highest to lowest priority):**
1. `MEMOIRE_PAT` environment variable
2. `~/.config/memoire-tui/config.toml` — `[auth]` section, `pat` key
3. Interactive prompt on first run (stores to config file)

**API URL resolution:**
1. `MEMOIRE_API_URL` environment variable
2. `~/.config/memoire-tui/config.toml` — `[api]` section, `url` key

**Wire format:** Every request sets `Authorization: Bearer <pat>`.

**Constraint:** The `/tokens` Lambda rejects PAT-authenticated requests (JWT only). The tokens screen must display a clear notice and disable create/delete when the TUI session is PAT-authenticated. This is the only endpoint with this restriction.

**Config file example:**
```toml
[api]
url = "https://api.memoire.example.com"

[auth]
pat = "pat_abc123"
```

---

## Screen Routing

The root `app.Model` holds:
- `currentScreen Screen` — which feature is active
- `screens map[Screen]tea.Model` — lazy-initialized screen models (initialized on first visit)
- `sidebar sidebarModel` — navigation state
- `statusBar statusBarModel` — shared status/message bar
- `flashMsg string`, `flashExpiry time.Time` — transient status messages

Screen transitions happen via a `NavigateTo(screen)` message. The sidebar and number-key shortcuts both emit this message.

---

## Async API Calls

All HTTP calls use `tea.Cmd` (non-blocking). Pattern:

```go
func fetchTasks(client *api.Client, userID string) tea.Cmd {
    return func() tea.Msg {
        tasks, err := client.ListTasks()
        if err != nil {
            return errMsg{err}
        }
        return tasksLoadedMsg{tasks}
    }
}
```

Loading states use `spinner.Model`. Errors surface in the status bar with a 4-second auto-dismiss.

---

## Feature Adaptation Notes

| Feature | Adaptation |
|---------|-----------|
| Diagrams | List view only. Detail shows JSON elements. "Open in editor" via `$EDITOR`. Canvas editing not possible in terminal. |
| Note images/attachments | List attachment filenames. "Open" key launches `xdg-open`/`open` with presigned URL via `$BROWSER`. |
| Note rich text | Render markdown via `glamour` (charmbracelet/glamour) in a `viewport.Model`. Edit in `$EDITOR` (tmp file, write back). |
| Assistant chat | Streaming via SSE or polling. Multiline input via `$EDITOR` or textarea. Output in scrollable viewport. |
| Export | Trigger download, display presigned URL or save path. No ZIP extraction in TUI. |
| Home/admin | Read-only stats table. Only visible when user ID is in ADMIN_USER_IDS (checked via API response). |
| Feeds articles | Read articles inline via viewport. External open via `$BROWSER` for full page. |

---

## Dependencies and Task Order

```
Task #1 (architecture)  — architect          [DONE when this doc is written]
Task #2 (feature map)   — memoire-expert     [parallel with #3]
Task #3 (UX doc)        — tui-expert         [parallel with #2]
Task #4 (Go bootstrap)  — golang-expert      [after #1; outputs: go.mod, client.go, app.go skeleton]
Task #5 (screens)       — all               [after #2, #3, #4; split into per-feature subtasks]
```

Task #5 will be broken into per-feature subtasks once #2 (FEATURES.md) and #3 (UX.md) land and the Go skeleton is buildable.

---

## Key Design Constraints (from CLAUDE.md)

- No emojis anywhere — not in UI strings, help text, status bar, or comments.
- New code lives under `tui/` only. The existing Python/Terraform codebase is untouched.
- Feature branch only; no push to main without user confirmation.
- Go module path: `github.com/neilfarmer/memoire/tui` (adjust if repo path differs).
- No build step for the existing frontend; TUI is a separate binary.
