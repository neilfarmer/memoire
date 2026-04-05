# Features

Memoire is a personal productivity app. All features are accessible from the left sidebar and from the AI assistant.

---

## Tasks

Create and track tasks with:
- **Title and description**
- **Status** — To Do, In Progress, Done
- **Priority** — Low, Medium, High
- **Due date** — tasks past their due date are marked overdue; tasks due today are highlighted
- **Folders** — organise tasks into user-created folders (e.g. Work, Personal, Side Projects)

Tasks that are due today or in progress appear on the home dashboard.

**Pomodoro timer** — built into the Tasks page. Focus a specific task; the timer tracks 25-minute work intervals and 5-minute breaks. Cycles are counted per session.

**Push notifications (ntfy)** — configure your [ntfy](https://ntfy.sh) topic URL in Settings to receive notifications for tasks that are due, overdue, or approaching their due date (1 hour, 1 day, 3 days in advance). Recurring reminders are also supported. Notifications are deduplicated so you won't receive the same alert twice in the same window.

---

## Habits

Define habits you want to do every day and mark them complete.

- **Streak tracking** — current streak and best streak per habit
- **30-day heatmap** — a calendar showing which days you completed each habit
- **Daily reminder (ntfy)** — set a time (UTC) and receive a push notification if a habit isn't marked done
- **Home dashboard** — shows today's completion count (e.g. "3 / 7 completed today")

---

## Goals

Track long-term goals alongside your daily work.

- Title, description, and optional target date
- Status — Active, Completed, Abandoned
- Progress percentage (0–100%)
- Filter view by status
- Active goals appear on the home dashboard

Goals are intentionally simple — no milestones or sub-tasks. The idea is to keep your long-term direction visible without turning goal-tracking into a project management tool.

---

## Journal

One entry per day with a full-screen markdown editor.

- **Mood** — Great, Good, Okay, Bad, Terrible
- **Tags** — freeform tags per entry
- **Auto-save** — configurable interval (30s, 1m, 2m, 5m) in Settings
- **Calendar view** — dots on days with entries; click a day to read that entry
- **Streak tracking** — current and longest streak
- **Full-text search** — search across all journal entries

---

## Notes

Markdown notes organised in a folder hierarchy.

- **Folder tree** — create folders and subfolders; drag notes between them
- **Full-screen markdown editor** — formatting toolbar with bold, italic, headings, code, lists, and links
- **Image attachments** — paste or upload images; they're stored in S3 and rendered inline
- **File attachments** — attach arbitrary files to a note; displayed as download links
- **Auto-save** — same configurable interval as the journal editor
- **Search** — full-text search across all notes

---

## Nutrition

Log meals and track daily macros.

- Log meals by name with optional calories, protein, carbs, and fat
- **USDA lookup** — when the AI assistant logs a meal, it queries the USDA FoodData Central API for accurate nutrition data automatically (no guessing)
- Daily macro totals calculated automatically
- Calendar view — click a past date to review what you ate
- Freeform notes field per day's log

---

## Exercise

Log workouts by day.

- Each log can have multiple exercises
- Each exercise has sets with reps and weight, plus a total duration
- Freeform notes field per log
- Calendar view showing which days have workout entries

---

## Home Dashboard

The first screen after login. Shows:

- **Greeting** and today's date
- **Tasks widget** — active and in-progress tasks due soon
- **Habits widget** — today's habit completion count and habit list
- **Journal widget** — current streak and link to today's entry
- **Goals widget** — active goals with progress
- **AWS cost widget** — current month's spend from Cost Explorer (requires Cost Explorer enabled and the `Project` tag activated — see [Getting Started](getting-started.md))

---

## AI Assistant (Pip)

A conversational assistant powered by Amazon Bedrock (Nova Lite by default, switchable to Nova Pro). Pip can create, read, update, and delete data across every feature using natural language.

The assistant panel slides in from the right side of the screen. It persists memory about you across sessions — facts you share are stored and loaded into every conversation.

Full documentation: [docs/features-ai-pal.md](features-ai-pal.md)

---

## Export

Downloads a ZIP of all your data as Markdown files, organised by feature:

- Journal entries with frontmatter (date, mood, tags)
- Notes organised in their folder hierarchy, with attachments included
- Tasks, habits, goals as structured Markdown

---

## Settings

| Setting | Description |
|---|---|
| Display name | Shown in the home greeting |
| Timezone | Used for date calculations (defaults to browser timezone) |
| Dark mode | Persisted per user |
| Colour theme | 11 themes — see [Themes](features-themes.md) |
| ntfy URL | Push notification endpoint for tasks and habits |
| Auto-save interval | How frequently the note and journal editors save (30s / 1m / 2m / 5m) |
| AI Pal name | The name shown in the assistant panel header (default: Pip) |

---

## Admin Dashboard

Accessible to users listed in the `admin_user_ids` Terraform variable. Shows a breakdown of Amazon Bedrock usage across all users.

Full documentation: [docs/features-admin.md](features-admin.md)
