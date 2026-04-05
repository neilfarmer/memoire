# AI Pal (Pip)

A conversational AI assistant embedded in the Memoire frontend, powered by Amazon Bedrock. The pal can create, read, update, and delete data across all features of the app by calling tools backed by the existing DynamoDB tables.

---

## Architecture

```
Browser (chat UI)
  └── POST /assistant/chat  →  Lambda (assistant)
                                  ├── Load conversation history (DynamoDB)
                                  ├── Load user memory (DynamoDB)
                                  ├── Bedrock converse() loop (up to 6 tool calls)
                                  │     └── Tool handlers → DynamoDB reads/writes
                                  ├── Save messages (DynamoDB)
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
- **Clear chat** — deletes all stored conversation history for the user via `DELETE /assistant/history`
- **Usage stats panel** — shows per-model token counts and estimated cost (Nova Lite/Pro pricing baked in to the frontend)
- **Voice input button** — uses the browser's Web Speech API to transcribe speech into the input box; auto-restarts on silence to stay active until manually stopped

---

## Conversation Memory

Two layers of memory persist across sessions:

### Short-term: message history
- Stored in the `assistant_conversations` DynamoDB table
- Up to 20 most recent messages are loaded as context on each request
- Consecutive same-role messages are merged (Bedrock requires alternating user/assistant)
- Messages have a 30-day TTL

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
- **Model selector** — Nova Lite (fast, cheap) or Nova Pro (slower, more capable); persisted in `localStorage`

---

## Terraform Variables

| Variable | Description | Default |
|---|---|---|
| `assistant_model_id` | Bedrock model ID | `us.amazon.nova-lite-v1:0` |
| `assistant_system_prompt` | Override system prompt | `""` (uses code default) |
| `usda_api_key` | USDA FoodData Central API key | `""` |

`usda_api_key` is read from 1Password (`op://homelab/usda-token/password`) in `scripts/load-env.sh` and passed through as `TF_VAR_usda_api_key`.

---

## Lambda Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/assistant/chat` | Send a message; returns reply + tools_used |
| `GET` | `/assistant/history` | Load conversation history |
| `DELETE` | `/assistant/history` | Clear conversation history |
| `GET` | `/assistant/usage` | Load per-model token usage |
