# AI Pal (Pip)

A conversational AI assistant embedded in the Memoire frontend, powered by Amazon Bedrock. The pal can create, read, update, and delete data across all features of the app by calling tools backed by the existing DynamoDB tables.

---

## Architecture

```
Browser (chat UI)
  └── POST /assistant/chat  →  Lambda (assistant)
                                  ├── Resolve conversation_id (auto-create if missing)
                                  ├── Load thread history (DynamoDB, scoped to conversation_id)
                                  ├── Load user memory (DynamoDB)
                                  ├── Bedrock converse() loop (up to 6 tool calls)
                                  │     └── Tool handlers → DynamoDB reads/writes
                                  ├── Save messages under conversation_id (DynamoDB)
                                  ├── Touch thread metadata (updated_at, message_count)
                                  ├── Update model usage counters (DynamoDB)
                                  └── Update master context summary (Bedrock)
```

**Model:** Amazon Nova Lite (`us.amazon.nova-lite-v1:0`) by default, switchable to Nova Pro via the UI.  
**Model ID** is a Terraform variable (`assistant_model_id`) — can be overridden per environment without code changes.  
**System prompt** is also a Terraform variable (`assistant_system_prompt`) — overridable without code changes.

---

## Chat UI

The pal panel slides in from the right side of the screen. It is independent of the main app navigation.

- **Model selector** — toggle between Nova Lite and Nova Pro per-session (stored in `localStorage`)
- **Clickable item links** — when the AI creates a task, note, goal, or journal entry it appends a `[pal-link:...]` tag; the frontend renders these as links that navigate directly to the created item
- **Auto-refresh** — after the AI calls a mutating tool (create/update/delete), the relevant UI section (task list, habit list, etc.) refreshes automatically without a page reload
- **Saved chats sidebar** — under the Library group in the left pane, the **AI Pal Chats** section lists all saved threads ordered by most-recent activity. Hovering the header reveals a "+" to start a new chat; hovering any row reveals rename/delete actions. The active thread is highlighted.
- **Auto-threading** — the first message in a new session auto-creates a thread titled from the first user line (truncated to 60 chars). Subsequent messages continue the same thread. Switching threads in the sidebar loads its messages and makes it active.
- **Delete chat** — the chat header's clear button deletes only the *currently open* thread via `DELETE /assistant/conversations/{id}` (prompts for confirmation). Wiping everything still works via `DELETE /assistant/history`.
- **Usage stats panel** — shows per-model token counts and estimated cost (Nova Lite/Pro pricing baked in to the frontend)
- **Voice input button** — uses the browser's Web Speech API to transcribe speech into the input box; auto-restarts on silence to stay active until manually stopped

---

## Conversation Memory

Two layers of memory persist across sessions:

### Short-term: message history
- Stored in the `assistant_conversations` DynamoDB table, keyed by `user_id` (PK) + `msg_id` (SK).
- Each message row carries a `conversation_id` attribute identifying its thread. Each thread also has a metadata row with `msg_id = __meta__#{conversation_id}` holding `title`, `created_at`, `updated_at`, and `message_count`.
- Up to 20 most recent messages **from the current thread only** are loaded as Bedrock context on each request.
- Consecutive same-role messages are merged (Bedrock requires alternating user/assistant).
- Message TTL is configurable per user via the **Chat retention** setting (default 30 days; `0` = keep forever). Metadata rows are never TTL'd and are only removed when the user deletes the thread.

### Long-term: user facts + master context
- **Facts** (`remember_fact` tool): key/value pairs stored in `assistant_memory` table; loaded into the system prompt on each request
- **Master context**: after every exchange, a second Bedrock call summarises everything known about the user into a 3–5 sentence paragraph; this is prepended to the system prompt as persistent background

---

## Tools

All tools are defined in `lambda/assistant/tools.py` in Bedrock converse format.

### Tasks
| Tool | Action |
|---|---|
| `create_task(title, description?, due_date?, priority?)` | Creates a task; returns a pal-link to it |
| `list_tasks(status?)` | Lists up to 50 tasks sorted by due date (soonest first); each entry includes `[id:...]` for use in complete/delete |
| `complete_task(task_id)` | Marks a task as done |
| `delete_task(task_id)` | Permanently deletes a task |

### Notes
| Tool | Action |
|---|---|
| `create_note(title, body?, folder_name?)` | Creates a note; creates the folder if it doesn't exist |
| `list_notes(folder_name?)` | Lists notes, optionally filtered by folder |
| `delete_note(note_id)` | Permanently deletes a note |
| `create_note_folder(name)` | Creates a folder |
| `list_note_folders()` | Lists all folders |

### Habits
| Tool | Action |
|---|---|
| `create_habit(name, time_of_day?)` | Creates a daily habit |
| `list_habits()` | Lists all habits |
| `toggle_habit(habit_id)` | Marks habit complete/incomplete for today |
| `delete_habit(habit_id)` | Permanently deletes a habit |

### Goals
| Tool | Action |
|---|---|
| `create_goal(title, description?, target_date?)` | Creates a goal |
| `list_goals()` | Lists active goals with progress % |
| `update_goal_progress(goal_id, progress?, status?)` | Updates progress (0–100) or status |
| `delete_goal(goal_id)` | Permanently deletes a goal |

### Journal
| Tool | Action |
|---|---|
| `create_journal_entry(body, mood?, title?)` | Creates or updates today's entry (one entry per day) |

### Nutrition
| Tool | Action |
|---|---|
| `lookup_nutrition(food_name)` | Queries USDA FoodData Central API for accurate macros; called automatically before `log_meal` when the user hasn't provided values |
| `log_meal(name, calories?, protein_g?, carbs_g?, fat_g?, date?)` | Logs a food item to the nutrition log |
| `get_nutrition_log(date?)` | Returns logged meals and macro totals for a date |

**USDA lookup details:** Tries the Branded database first (has real serving sizes from product labels), falls back to Foundation/SR Legacy for generic foods. Sanity-checks results to skip entries with impossible calorie values (>900 kcal/100g). Requires `USDA_API_KEY` env var (set via 1Password → Terraform). The model is instructed to round calories up when uncertain about serving weight.

All numeric nutrition values are stored as `Decimal` in DynamoDB (boto3 does not accept Python floats).

### Exercise
| Tool | Action |
|---|---|
| `log_exercise(name, duration_min?, sets?, date?)` | Logs an exercise; sets is `[{reps, weight}]` |
| `get_exercise_log(date?)` | Returns logged exercises for a date |

### Memory
| Tool | Action |
|---|---|
| `remember_fact(key, value)` | Persists a fact about the user across sessions |

---

## Model Usage Tracking

After each exchange, token counts are atomically incremented in DynamoDB (`ADD` expression) keyed by model ID. The `GET /assistant/usage` endpoint returns per-model totals. The frontend calculates estimated cost using hardcoded Nova Lite/Pro pricing.

The admin dashboard (`/admin`) also shows a per-user breakdown of model usage across all users.

---

## Settings

- **Pal name** — configurable in Settings; defaults to "Pip"; stored server-side and rendered in the chat header
- **Chat retention** — how long chat messages persist before TTL expiry. Options: *Keep forever* (`0`), 7, 30 (default), 90, 180, or 365 days. Stored in the `settings` table as `chat_retention_days`. Changing it only affects messages saved **after** the change; already-persisted rows keep whatever TTL they were written with.
- **Model selector** — Nova Lite (fast, cheap) or Nova Pro (slower, more capable); persisted in `localStorage`

---

## Terraform Variables

| Variable | Description | Default |
|---|---|---|
| `assistant_model_id` | Bedrock model ID | `us.amazon.nova-lite-v1:0` |
| `assistant_system_prompt` | Override system prompt | `""` (uses code default) |
| `usda_api_key` | USDA FoodData Central API key | `""` |

### USDA FoodData Central API

**Docs:** https://fdc.nal.usda.gov/api-guide  
**Spec:** https://fdc.nal.usda.gov/api-spec/fdc_api.html  
**License:** CC0 1.0 Universal (public domain) — no restrictions on use  
**Citation (if needed):** "U.S. Department of Agriculture, Agricultural Research Service. FoodData Central, 2019."

#### Rate limits
- **1,000 requests/hour per IP address** — sufficient for personal use
- Exceeding the limit blocks the key for 1 hour
- Higher limits available by contacting USDA support
- A `DEMO_KEY` exists for testing but has tighter limits; use a real key in production

#### Getting a key and wiring it up
1. Go to https://fdc.nal.usda.gov/api-key-signup — register with email, key arrives immediately
2. Store it in 1Password as a new item named `usda-token`, with the key in the `password` field (vault: `homelab`)
3. `scripts/load-env.sh` reads it automatically: `op read "op://homelab/usda-token/password"` → `TF_VAR_usda_api_key`
4. Run `make deploy` (or `make deploy-auto`) — Terraform passes it to the Lambda as the `USDA_API_KEY` environment variable

The Lambda reads `os.environ["USDA_API_KEY"]` in `lambda/assistant/tools.py`. If the key is missing or the USDA API is unreachable, `lookup_nutrition` returns a graceful fallback and the model estimates from general knowledge.

#### Endpoints used
- `POST /foods/search` — searches by keyword with optional `dataType` filter (Branded, Foundation, SR Legacy)

---

## Lambda Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/assistant/chat` | Send a message. Accepts optional `conversation_id`; auto-creates a thread when omitted. Returns `reply`, `tools_used`, and `conversation_id`. |
| `GET` | `/assistant/conversations` | List saved threads (metadata only, ordered by most-recent update). |
| `POST` | `/assistant/conversations` | Explicitly create an empty thread. |
| `GET` | `/assistant/conversations/{id}` | Fetch a thread's metadata and full message list. |
| `PATCH` | `/assistant/conversations/{id}` | Rename a thread (`{ "title": "..." }`). |
| `DELETE` | `/assistant/conversations/{id}` | Delete a single thread and its messages. |
| `GET` | `/assistant/history` | Load the most-recent thread's messages (legacy; prefer `/assistant/conversations/{id}`). |
| `DELETE` | `/assistant/history` | Wipe *all* threads and messages for the user. |
| `GET` | `/assistant/usage` | Load per-model token usage. |
