# Memoire TUI — UX

This file documents the layout, key bindings, and interaction patterns. The
binary's `?` overlay regenerates the screen-specific section of this doc at
runtime.

## Window layout

```
+----------------------------------------------------------+
| memoire                          ● online  api.host      |  header
+----------+-----------------------------------------------+
|          |                                               |
| Sidebar  |  current screen                               |
|          |                                               |
+----------+-----------------------------------------------+
| Tasks   <flash msg>                          ? help q quit|  status bar
+----------------------------------------------------------+
```

- Sidebar lists every screen with a numeric prefix (1..9).
- Header shows app name, current section, and reachability indicator.
- Status bar shows screen, transient flash messages (4s TTL), and per-screen
  key hints.
- `?` overlays a centred dialog with global + current-screen key bindings.

## Global keys

| Key | Action |
|-----|--------|
| `?` | toggle help overlay |
| `ctrl+q` | quit |
| `1`–`9` | jump to first 9 sidebar entries |
| `g <letter>` | leader nav: `g d` dashboard, `g t` tasks, `g n` notes, `g j` journal, `g h` habits, `g o` goals, `g H` health, `g u` nutrition, `g f` finances, `g r` feeds, `g b` bookmarks, `g v` favorites, `g a` assistant, `g s` settings, `g k` tokens, `g x` admin |
| `ctrl+r` | refresh current screen |

## Screen patterns

Every CRUD screen follows the same three-state Bubble Tea machine:

- **list** — `bubbles/list.Model` with built-in `/` filter
- **detail** — viewport with `glamour` markdown rendering where applicable
- **form** — `huh.Form` with field validation; `esc` cancels

Common keys inside a screen:

| Key | Action |
|-----|--------|
| `enter` | open detail (or, in two-pane screens, focus into the right pane) |
| `n` | new entry |
| `e` | edit selected |
| `d` | delete selected (always followed by a `y`/`n` confirm dialog) |
| `r` | refresh |
| `tab` | switch between left/right or tabs |
| `/` | filter list |
| `ctrl+e` (form) | open `$EDITOR` on a tmpfile and reload |

## Notes-specific

- Two-pane: folder tree on the left, notes on the right.
- `f` creates a new folder.
- Tags entered as comma-separated strings.

## Journal-specific

- Calendar dot markers show dates with entries (loaded from `GET /journal`).
- `← / →` step day; `↑ / ↓` step week; `t` jumps to today; `n / p` aliases.

## Habits-specific

- 30-day history rendered as `■` (done) / `·` (empty).
- `space` toggles today; `t` toggles a chosen date (date picker not yet
  implemented — current cursor only).

## Tasks-specific

- Filter pills cycle on `f` (all → todo → in-progress → done).
- Sort cycles on `s` (smart → due → priority → title).
- `c` opens the 7-day agenda; `a` triggers `/tasks/auto-schedule`.

## Health / Nutrition

- Day-keyed: `← / →` step day, `t` jumps to today.
- Health: `e` edits totals, `T` shows 7-day summary stats (no charts).
- Nutrition: `n` adds a meal, `x` removes the last meal, `d` deletes the day.

## Finances

- `tab` cycles tabs (debts / income / expenses).
- Summary header pulls from `/finances/summary`.

## Feeds

- Left pane: feeds list. Right pane: articles list.
- `enter` opens the article in an inline reader (calls
  `/feeds/article-text`). `o` opens externally. `h` favorites.
  `r` (in detail) marks read.

## Assistant

- Three panes: conversations (left), messages (centre, viewport), input
  (bottom textarea). `tab` cycles focus.
- `ctrl+j` sends. `ctrl+m` toggles model (nova-lite / nova-pro). `ctrl+l`
  clears the current conversation. `ctrl+n` starts a new one.
- Streaming is not used; a spinner indicates "sending" and the reply is
  rendered all at once via glamour.

## Settings

- Sectioned read-only view.
- `e` opens an edit form; `x` triggers `/export` and prints the presigned
  URL; `T` sends a test ntfy notification.

## Tokens

- When the API returns 403 to `GET /tokens` (PAT auth), the screen displays
  a banner and disables `n` / `d`.
- After create, the plaintext token is shown once in a centred dialog.
  `enter` or `esc` dismisses.

## Admin

- Two read-only tables (Costs and Stats). The screen stays available but
  prints "(unavailable)" when the API responds with 4xx for non-admin users.

## Theming

- Adaptive colour palette (`internal/styles/styles.go`) auto-switches based
  on terminal background.
- Primary indigo `#4f46e5` / `#818cf8`, accent amber `#d97706` / `#f59e0b`.
- `--no-color` (or `NO_COLOR=1`) disables coloured output.
