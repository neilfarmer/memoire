# Memoire TUI — Feature & API map

Companion to `ARCHITECTURE.md`. For every feature: which API endpoints the
TUI uses, which DTOs back them, and which screen renders them.

All endpoints authenticate via PAT against the same Lambda authorizer the SPA
uses. The only screen that special-cases auth is **Tokens**, which the
`/tokens` Lambda rejects when called with a PAT (the screen renders a banner
and disables create/delete in that case).

| Feature | Screen | Endpoints | Notes |
|---------|--------|-----------|-------|
| Tasks | `screens/tasks.go` | `GET/POST/PUT/DELETE /tasks{,/id}`, `GET /tasks/calendar?from&to`, `POST /tasks/auto-schedule` | Filter/sort/group + 7-day agenda + auto-schedule |
| Notes | `screens/notes.go` | `GET/POST/PUT/DELETE /notes{,/id}`, `GET/POST/PUT/DELETE /notes/folders{,/id}`, `POST /notes/images`, `POST/GET/DELETE /notes/{id}/attachments{,/aid}` | `$EDITOR` for body, glamour render, attachment URLs handed off to `$BROWSER` |
| Habits | `screens/habits.go` | `GET/POST/PUT/DELETE /habits{,/id}`, `POST /habits/{id}/toggle?date=` | 30-day ASCII history, current/best streak |
| Journal | `screens/journal.go` | `GET /journal?q=`, `GET/PUT/DELETE /journal/{date}` | Month calendar with markers, mood pills, `$EDITOR` for body |
| Goals | `screens/goals.go` | `GET/POST/PUT/DELETE /goals{,/id}` | Status filter, progress bar |
| Health | `screens/health.go` | `GET /health`, `GET/PUT/DELETE /health/{date}`, `GET /health/summary?days=`, `GET /health/exercises/recent?q&days&limit`, `GET /health/history?days=` | Trends summary replaces sparkline charts |
| Nutrition | `screens/nutrition.go` | `GET /nutrition`, `GET/PUT/DELETE /nutrition/{date}`, `GET /nutrition/summary`, `GET /nutrition/meals/recent` | Day-keyed meal log, totals row |
| Finances | `screens/finances.go` | `/debts`, `/income`, `/fixed-expenses` (full CRUD each), `GET /finances/summary` | Three tabs + summary header |
| Feeds | `screens/feeds.go` | `GET/POST/DELETE /feeds{,/id}`, `GET /feeds/articles?force=`, `GET /feeds/article-text?url=`, `POST /feeds/read`, `POST /favorites` (heart) | Two-pane reader, inline article via glamour |
| Bookmarks | `screens/bookmarks.go` | `GET/POST/PUT/DELETE /bookmarks{,/id}` (with `q` and `tag`) | Built-in `/` filter, browser open |
| Favorites | `screens/favorites.go` | `GET /favorites`, `POST /favorites`, `PATCH /favorites/{id}`, `DELETE /favorites/{id}` | Read-mostly; remove + open |
| Settings | `screens/settings.go` | `GET/PUT /settings`, `POST /settings/test-notification`, `GET /export` | Sectioned form; export prints presigned URL |
| Tokens | `screens/tokens.go` | `GET/POST/DELETE /tokens{,/id}` | PAT-aware banner; secret shown once on create |
| Assistant | `screens/assistant.go` | `POST /assistant/chat`, `GET/POST/PATCH/DELETE /assistant/conversations{,/id}`, `GET/DELETE /assistant/history`, `GET /assistant/usage`, `GET/PUT /assistant/memory`, `PUT /assistant/memory/facts/{key}`, `DELETE /assistant/memory/{key}`, `GET/PUT /assistant/profile`, `POST /assistant/profile/analyze`, `POST /assistant/profile/cleanup` | Spinner-then-render (no SSE), nova-lite/nova-pro toggle |
| Admin | `screens/admin.go` | `GET /home/costs`, `GET /admin/stats` | Read-only; failures render "(unavailable)" |
| Dashboard | `screens/dashboard.go` | `GET /tasks`, `GET /habits`, `GET /notes` | Today / streak / latest snapshot |

## Diagrams omission

Diagrams (canvas drawing) is intentionally absent. The terminal cannot render
the SPA's editing surface and the user explicitly opted to drop the screen
rather than ship a JSON-only adaptation. The endpoints (`/diagrams`,
`/diagrams/{id}`) remain reachable from the API client surface only via the
shared `*api.Client` helpers; no typed wrappers are exposed.

## Auth headers

All requests:

```
Authorization: Bearer <pat>
Accept: application/json
Content-Type: application/json   # only when a body is present
```

`internal/api/client.go` parses non-2xx bodies for `error`/`message` JSON
keys, surfaces them as `*api.APIError`, and joins `ErrPATForbidden` with the
APIError when the rejected route was under `/tokens`.
