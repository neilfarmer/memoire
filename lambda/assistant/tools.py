"""Bedrock tool definitions and handlers for the AI assistant."""

import json
import logging
import os
import urllib.parse
import urllib.request
import uuid
from decimal import Decimal
from datetime import date, datetime, timezone

import db
import memory as mem

logger = logging.getLogger(__name__)

# ── Table env vars ────────────────────────────────────────────────────────────

TASKS_TABLE        = os.environ["TASKS_TABLE"]
NOTES_TABLE        = os.environ["NOTES_TABLE"]
NOTE_FOLDERS_TABLE = os.environ["NOTE_FOLDERS_TABLE"]
HABITS_TABLE       = os.environ["HABITS_TABLE"]
GOALS_TABLE        = os.environ["GOALS_TABLE"]
JOURNAL_TABLE      = os.environ["JOURNAL_TABLE"]
NUTRITION_TABLE    = os.environ["NUTRITION_TABLE"]
HEALTH_TABLE       = os.environ["HEALTH_TABLE"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Tool spec definitions (Bedrock converse format) ───────────────────────────

TOOL_SPECS = [
    {
        "toolSpec": {
            "name": "create_task",
            "description": "Create a new task for the user in their task list.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "title":       {"type": "string", "description": "Task title (required)"},
                        "description": {"type": "string", "description": "Optional details"},
                        "due_date":    {"type": "string", "description": "Due date in YYYY-MM-DD format"},
                        "priority":    {"type": "string", "enum": ["low", "medium", "high"]},
                    },
                    "required": ["title"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "list_tasks",
            "description": "List the user's current tasks.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["todo", "in_progress", "done", "all"],
                            "description": "Filter by status. Defaults to active tasks (todo + in_progress).",
                        }
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "create_note",
            "description": "Create a new note for the user, optionally inside a folder.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "title":       {"type": "string", "description": "Note title"},
                        "body":        {"type": "string", "description": "Note body / content"},
                        "folder_name": {"type": "string", "description": "Name of the folder to put the note in. The folder will be created if it doesn't exist."},
                    },
                    "required": ["title"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "create_note_folder",
            "description": "Create a new folder to organize notes.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Folder name (required)"},
                    },
                    "required": ["name"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "list_note_folders",
            "description": "List the user's note folders.",
            "inputSchema": {
                "json": {"type": "object", "properties": {}},
            },
        }
    },
    {
        "toolSpec": {
            "name": "create_habit",
            "description": "Create a new habit for the user to track daily.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "name":        {"type": "string", "description": "Habit name (required)"},
                        "time_of_day": {
                            "type": "string",
                            "enum": ["morning", "afternoon", "evening", "anytime"],
                            "description": "When to do the habit",
                        },
                    },
                    "required": ["name"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "list_habits",
            "description": "List the user's current habits.",
            "inputSchema": {
                "json": {"type": "object", "properties": {}},
            },
        }
    },
    {
        "toolSpec": {
            "name": "create_goal",
            "description": "Create a new goal for the user.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "title":       {"type": "string", "description": "Goal title (required)"},
                        "description": {"type": "string"},
                        "target_date": {"type": "string", "description": "Target completion date YYYY-MM-DD"},
                    },
                    "required": ["title"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "list_goals",
            "description": "List the user's current goals.",
            "inputSchema": {
                "json": {"type": "object", "properties": {}},
            },
        }
    },
    {
        "toolSpec": {
            "name": "create_journal_entry",
            "description": "Create or update today's journal entry for the user.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "body":  {"type": "string", "description": "Journal entry content (required)"},
                        "mood":  {"type": "string", "enum": ["great", "good", "okay", "bad", "terrible"]},
                        "title": {"type": "string"},
                    },
                    "required": ["body"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "complete_task",
            "description": "Mark a task as done. Use list_tasks first to find the task_id.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "The task_id to mark as done"},
                    },
                    "required": ["task_id"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "delete_task",
            "description": "Permanently delete a task. Use list_tasks first to find the task_id.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "The task_id to delete"},
                    },
                    "required": ["task_id"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "list_notes",
            "description": "List the user's notes, optionally filtered by folder.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "folder_name": {"type": "string", "description": "Filter notes by folder name (optional)"},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "delete_note",
            "description": "Permanently delete a note. Use list_notes first to find the note_id.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "note_id": {"type": "string", "description": "The note_id to delete"},
                    },
                    "required": ["note_id"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "toggle_habit",
            "description": "Mark a habit as completed for today (or un-complete it if already done). Use list_habits first to find the habit_id.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "habit_id": {"type": "string", "description": "The habit_id to toggle"},
                    },
                    "required": ["habit_id"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "delete_habit",
            "description": "Permanently delete a habit. Use list_habits first to find the habit_id.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "habit_id": {"type": "string", "description": "The habit_id to delete"},
                    },
                    "required": ["habit_id"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "update_goal_progress",
            "description": "Update the progress percentage (0-100) or status of a goal. Use list_goals first to find the goal_id.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "goal_id":  {"type": "string", "description": "The goal_id to update"},
                        "progress": {"type": "integer", "description": "Progress percentage 0-100"},
                        "status":   {"type": "string", "enum": ["active", "completed", "abandoned"]},
                    },
                    "required": ["goal_id"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "delete_goal",
            "description": "Permanently delete a goal. Use list_goals first to find the goal_id.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "goal_id": {"type": "string", "description": "The goal_id to delete"},
                    },
                    "required": ["goal_id"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "log_meal",
            "description": (
                "Log a food item to the nutrition log for a given date (defaults to today). "
                "Use this — NOT create_journal_entry — for ANY food, meal, eating, calorie, "
                "macro, or diet tracking request. When the user mentions 'food journal', "
                "'nutrition', 'calories', or what they ate, always use this tool."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "name":      {"type": "string", "description": "Food item name, e.g. 'Chorizo with cheese dip'"},
                        "calories":  {"type": "number", "description": "Calories (kcal)"},
                        "protein_g": {"type": "number", "description": "Protein in grams"},
                        "carbs_g":   {"type": "number", "description": "Carbohydrates in grams"},
                        "fat_g":     {"type": "number", "description": "Fat in grams"},
                        "date":      {"type": "string", "description": "Date YYYY-MM-DD, defaults to today"},
                    },
                    "required": ["name"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_nutrition_log",
            "description": "Get the nutrition log for a date to see what has been eaten and macro totals.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "description": "Date YYYY-MM-DD, defaults to today"},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "log_exercise",
            "description": (
                "Log an exercise to the exercise log for a given date (defaults to today). "
                "Use this — NOT create_journal_entry — for ANY workout, exercise, gym, "
                "run, swim, lift, or physical activity tracking request."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "name":         {"type": "string", "description": "Exercise name, e.g. 'Bench Press' or 'Morning run'"},
                        "duration_min": {"type": "number", "description": "Duration in minutes (for cardio or timed exercises)"},
                        "sets": {
                            "type": "array",
                            "description": "Sets for strength exercises, e.g. [{\"reps\": 10, \"weight\": 135}]",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "reps":   {"type": "number"},
                                    "weight": {"type": "number", "description": "Weight in lbs"},
                                },
                            },
                        },
                        "date": {"type": "string", "description": "Date YYYY-MM-DD, defaults to today"},
                    },
                    "required": ["name"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_exercise_log",
            "description": "Get the exercise log for a date to see what workouts were recorded.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "description": "Date YYYY-MM-DD, defaults to today"},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "lookup_nutrition",
            "description": (
                "Look up accurate nutrition facts for a food item from the USDA database. "
                "Call this before log_meal whenever the user has not explicitly provided calorie/macro values."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "food_name": {"type": "string", "description": "Food name to search, e.g. 'pizza rolls' or 'banana'"},
                    },
                    "required": ["food_name"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "remember_fact",
            "description": "Remember a fact about the user for future conversations.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "key":   {"type": "string", "description": "Short label for the fact, e.g. 'wake_time'"},
                        "value": {"type": "string", "description": "The fact to remember"},
                    },
                    "required": ["key", "value"],
                }
            },
        }
    },
]


# ── Tool handlers ─────────────────────────────────────────────────────────────

def handle_tool(user_id: str, name: str, inputs: dict, local_date: str | None = None) -> str:
    _today = local_date or date.today().isoformat()
    handlers = {
        "create_task":          _create_task,
        "list_tasks":           _list_tasks,
        "complete_task":        _complete_task,
        "delete_task":          _delete_task,
        "create_note":          _create_note,
        "list_notes":           _list_notes,
        "delete_note":          _delete_note,
        "create_note_folder":   _create_note_folder,
        "list_note_folders":    _list_note_folders,
        "create_habit":         _create_habit,
        "list_habits":          _list_habits,
        "toggle_habit":         _toggle_habit,
        "delete_habit":         _delete_habit,
        "create_goal":          _create_goal,
        "list_goals":           _list_goals,
        "update_goal_progress": _update_goal_progress,
        "delete_goal":          _delete_goal,
        "create_journal_entry": _create_journal_entry,
        "log_meal":             _log_meal,
        "get_nutrition_log":    _get_nutrition_log,
        "log_exercise":         _log_exercise,
        "get_exercise_log":     _get_exercise_log,
        "lookup_nutrition":     _lookup_nutrition,
        "remember_fact":        _remember_fact,
    }
    handler = handlers.get(name)
    if not handler:
        return f"Unknown tool: {name}"
    # Inject local today for tools that default to "today"
    _date_aware = {"log_meal", "get_nutrition_log", "log_exercise", "get_exercise_log",
                   "create_journal_entry", "toggle_habit"}
    if name in _date_aware:
        inputs = {**inputs, "_today": _today}
    return handler(user_id, inputs)


def _create_task(user_id: str, inputs: dict) -> str:
    table = db.get_table(TASKS_TABLE)
    now   = _now()
    task  = {
        "user_id":    user_id,
        "task_id":    str(uuid.uuid4()),
        "title":      inputs["title"].strip(),
        "description": inputs.get("description", ""),
        "status":     "todo",
        "priority":   inputs.get("priority", "medium"),
        "created_at": now,
        "updated_at": now,
    }
    if inputs.get("due_date"):
        task["due_date"] = inputs["due_date"]
    task = {k: v for k, v in task.items() if v is not None and v != ""}
    table.put_item(Item=task)
    return f"Created task: {task['title']} [pal-link:task:{task['task_id']}:Open task →]"


def _list_tasks(user_id: str, inputs: dict) -> str:
    table  = db.get_table(TASKS_TABLE)
    tasks  = db.query_by_user(table, user_id)
    status = inputs.get("status", "active")

    if status == "all":
        filtered = tasks
    elif status in ("todo", "in_progress", "done"):
        filtered = [t for t in tasks if t.get("status") == status]
    else:
        filtered = [t for t in tasks if t.get("status") in ("todo", "in_progress")]

    if not filtered:
        return "No tasks found."

    # Sort: tasks with a due_date first (earliest first), then undated tasks by created_at
    def _sort_key(t):
        due = t.get("due_date") or ""
        return (0 if due else 1, due or t.get("created_at", ""))

    filtered.sort(key=_sort_key)

    lines = []
    for t in filtered[:50]:
        due  = f" (due {t['due_date']})" if t.get("due_date") else ""
        lines.append(f"- [{t.get('status', 'todo')}] {t['title']}{due} [id:{t['task_id']}]")
    return "\n".join(lines)


def _get_or_create_folder(user_id: str, folder_name: str) -> str:
    """Return folder_id for the named folder, creating it if needed."""
    table   = db.get_table(NOTE_FOLDERS_TABLE)
    folders = db.query_by_user(table, user_id)
    name_lower = folder_name.strip().lower()
    for f in folders:
        if f.get("name", "").lower() == name_lower:
            return f["folder_id"]
    # Create it
    folder_id = str(uuid.uuid4())
    table.put_item(Item={
        "user_id":    user_id,
        "folder_id":  folder_id,
        "name":       folder_name.strip(),
        "created_at": _now(),
    })
    return folder_id


def _create_note(user_id: str, inputs: dict) -> str:
    table     = db.get_table(NOTES_TABLE)
    now       = _now()
    folder_id = None
    if inputs.get("folder_name"):
        folder_id = _get_or_create_folder(user_id, inputs["folder_name"])
    note = {
        "user_id":    user_id,
        "note_id":    str(uuid.uuid4()),
        "title":      inputs.get("title", "").strip(),
        "body":       inputs.get("body", ""),
        "created_at": now,
        "updated_at": now,
    }
    if folder_id:
        note["folder_id"] = folder_id
    note = {k: v for k, v in note.items() if v is not None}
    table.put_item(Item=note)
    location = f" in '{inputs['folder_name']}'" if inputs.get("folder_name") else ""
    return f"Created note: {note.get('title', '(untitled)')}{location} [pal-link:note:{note['note_id']}:Open note →]"


def _create_note_folder(user_id: str, inputs: dict) -> str:
    name = inputs.get("name", "").strip()
    table = db.get_table(NOTE_FOLDERS_TABLE)
    # Check if already exists
    folders = db.query_by_user(table, user_id)
    for f in folders:
        if f.get("name", "").lower() == name.lower():
            return f"Folder '{name}' already exists"
    table.put_item(Item={
        "user_id":    user_id,
        "folder_id":  str(uuid.uuid4()),
        "name":       name,
        "created_at": _now(),
    })
    return f"Created folder: {name}"


def _list_note_folders(user_id: str, inputs: dict) -> str:
    table   = db.get_table(NOTE_FOLDERS_TABLE)
    folders = db.query_by_user(table, user_id)
    if not folders:
        return "No note folders found."
    return "\n".join(f"- {f['name']}" for f in folders[:20])


def _create_habit(user_id: str, inputs: dict) -> str:
    table      = db.get_table(HABITS_TABLE)
    time_of_day = inputs.get("time_of_day", "anytime")
    habit      = {
        "user_id":     user_id,
        "habit_id":    str(uuid.uuid4()),
        "name":        inputs["name"].strip(),
        "time_of_day": time_of_day,
        "created_at":  date.today().isoformat(),
    }
    table.put_item(Item=habit)
    return f"Created habit: {habit['name']} ({time_of_day})"


def _list_habits(user_id: str, inputs: dict) -> str:
    table  = db.get_table(HABITS_TABLE)
    habits = db.query_by_user(table, user_id)
    if not habits:
        return "No habits found."
    lines = [f"- {h['name']} ({h.get('time_of_day', 'anytime')})" for h in habits[:20]]
    return "\n".join(lines)


def _create_goal(user_id: str, inputs: dict) -> str:
    table = db.get_table(GOALS_TABLE)
    now   = _now()
    goal  = {
        "user_id":     user_id,
        "goal_id":     str(uuid.uuid4()),
        "title":       inputs["title"].strip(),
        "description": inputs.get("description", ""),
        "status":      "active",
        "progress":    0,
        "created_at":  now,
        "updated_at":  now,
    }
    if inputs.get("target_date"):
        goal["target_date"] = inputs["target_date"]
    goal = {k: v for k, v in goal.items() if v is not None and v != ""}
    table.put_item(Item=goal)
    return f"Created goal: {goal['title']} [pal-link:goal:{goal['goal_id']}:Open goal →]"


def _list_goals(user_id: str, inputs: dict) -> str:
    table = db.get_table(GOALS_TABLE)
    goals = db.query_by_user(table, user_id)
    active = [g for g in goals if g.get("status") == "active"]
    if not active:
        return "No active goals found."
    lines = []
    for g in active[:10]:
        progress    = g.get("progress", 0)
        target_date = f" → {g['target_date']}" if g.get("target_date") else ""
        lines.append(f"- {g['title']} ({progress}%){target_date}")
    return "\n".join(lines)


def _complete_task(user_id: str, inputs: dict) -> str:
    table = db.get_table(TASKS_TABLE)
    task_id = inputs["task_id"]
    existing = db.get_item(table, user_id, "task_id", task_id)
    if not existing:
        return f"Task {task_id} not found."
    table.update_item(
        Key={"user_id": user_id, "task_id": task_id},
        UpdateExpression="SET #s = :s, updated_at = :u",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "done", ":u": _now()},
    )
    return f"Marked '{existing.get('title', task_id)}' as done."


def _delete_task(user_id: str, inputs: dict) -> str:
    table = db.get_table(TASKS_TABLE)
    task_id = inputs["task_id"]
    existing = db.get_item(table, user_id, "task_id", task_id)
    if not existing:
        return f"Task {task_id} not found."
    db.delete_item(table, user_id, "task_id", task_id)
    return f"Deleted task '{existing.get('title', task_id)}'."


def _list_notes(user_id: str, inputs: dict) -> str:
    notes_table   = db.get_table(NOTES_TABLE)
    folders_table = db.get_table(NOTE_FOLDERS_TABLE)
    notes = db.query_by_user(notes_table, user_id)

    folder_name = inputs.get("folder_name")
    if folder_name:
        folders = db.query_by_user(folders_table, user_id)
        folder_id = next(
            (f["folder_id"] for f in folders if f.get("name", "").lower() == folder_name.strip().lower()),
            None,
        )
        if not folder_id:
            return f"No folder named '{folder_name}' found."
        notes = [n for n in notes if n.get("folder_id") == folder_id]

    if not notes:
        return "No notes found."
    lines = [f"- [{n['note_id']}] {n.get('title', '(untitled)')}" for n in notes[:20]]
    return "\n".join(lines)


def _delete_note(user_id: str, inputs: dict) -> str:
    table = db.get_table(NOTES_TABLE)
    note_id = inputs["note_id"]
    existing = db.get_item(table, user_id, "note_id", note_id)
    if not existing:
        return f"Note {note_id} not found."
    db.delete_item(table, user_id, "note_id", note_id)
    return f"Deleted note '{existing.get('title', note_id)}'."


def _toggle_habit(user_id: str, inputs: dict) -> str:
    table    = db.get_table(HABITS_TABLE)
    habit_id = inputs["habit_id"]
    existing = db.get_item(table, user_id, "habit_id", habit_id)
    if not existing:
        return f"Habit {habit_id} not found."
    today = inputs.get("_today") or date.today().isoformat()
    history: list = existing.get("completion_history", [])
    if today in history:
        history.remove(today)
        action = "un-completed"
    else:
        history.append(today)
        action = "completed"
    table.update_item(
        Key={"user_id": user_id, "habit_id": habit_id},
        UpdateExpression="SET completion_history = :h",
        ExpressionAttributeValues={":h": history},
    )
    return f"{action.capitalize()} habit '{existing.get('name', habit_id)}' for today."


def _delete_habit(user_id: str, inputs: dict) -> str:
    table    = db.get_table(HABITS_TABLE)
    habit_id = inputs["habit_id"]
    existing = db.get_item(table, user_id, "habit_id", habit_id)
    if not existing:
        return f"Habit {habit_id} not found."
    db.delete_item(table, user_id, "habit_id", habit_id)
    return f"Deleted habit '{existing.get('name', habit_id)}'."


def _update_goal_progress(user_id: str, inputs: dict) -> str:
    table   = db.get_table(GOALS_TABLE)
    goal_id = inputs["goal_id"]
    existing = db.get_item(table, user_id, "goal_id", goal_id)
    if not existing:
        return f"Goal {goal_id} not found."
    updates = ["updated_at = :u"]
    values  = {":u": _now()}
    if "progress" in inputs:
        updates.append("progress = :p")
        values[":p"] = inputs["progress"]
    if "status" in inputs:
        updates.append("#s = :s")
        values[":s"] = inputs["status"]
    table.update_item(
        Key={"user_id": user_id, "goal_id": goal_id},
        UpdateExpression="SET " + ", ".join(updates),
        ExpressionAttributeNames={"#s": "status"} if "status" in inputs else {},
        ExpressionAttributeValues=values,
    )
    parts = []
    if "progress" in inputs:
        parts.append(f"progress to {inputs['progress']}%")
    if "status" in inputs:
        parts.append(f"status to {inputs['status']}")
    return f"Updated goal '{existing.get('title', goal_id)}': {', '.join(parts)}."


def _delete_goal(user_id: str, inputs: dict) -> str:
    table   = db.get_table(GOALS_TABLE)
    goal_id = inputs["goal_id"]
    existing = db.get_item(table, user_id, "goal_id", goal_id)
    if not existing:
        return f"Goal {goal_id} not found."
    db.delete_item(table, user_id, "goal_id", goal_id)
    return f"Deleted goal '{existing.get('title', goal_id)}'."


def _create_journal_entry(user_id: str, inputs: dict) -> str:
    table      = db.get_table(JOURNAL_TABLE)
    entry_date = inputs.get("_today") or date.today().isoformat()
    now        = _now()

    existing   = db.get_item(table, user_id, "entry_date", entry_date)
    created_at = existing["created_at"] if existing else now

    item = {
        "user_id":    user_id,
        "entry_date": entry_date,
        "title":      (inputs.get("title") or "").strip(),
        "body":       inputs.get("body", ""),
        "mood":       inputs.get("mood", ""),
        "created_at": created_at,
        "updated_at": now,
    }
    item = {k: v for k, v in item.items() if v is not None and v != ""}
    table.put_item(Item=item)
    action = "Updated" if existing else "Created"
    return f"{action} journal entry for {entry_date} [pal-link:journal:{entry_date}:Open entry →]"


def _log_meal(user_id: str, inputs: dict) -> str:
    table    = db.get_table(NUTRITION_TABLE)
    log_date = inputs.get("date") or inputs.get("_today") or date.today().isoformat()
    existing = table.get_item(Key={"user_id": user_id, "log_date": log_date}).get("Item")
    meals    = list(existing.get("meals", [])) if existing else []

    meal = {"id": str(uuid.uuid4()), "name": inputs["name"].strip()}
    for field in ("calories", "protein_g", "carbs_g", "fat_g"):
        if inputs.get(field) is not None:
            meal[field] = Decimal(str(inputs[field]))
    meals.append(meal)

    table.put_item(Item={
        "user_id":    user_id,
        "log_date":   log_date,
        "meals":      meals,
        "notes":      existing.get("notes", "") if existing else "",
        "created_at": existing["created_at"] if existing else _now(),
        "updated_at": _now(),
    })
    cal_str = f" ({int(meal['calories'])} cal)" if meal.get("calories") else ""
    return f"Logged '{meal['name']}'{cal_str} to nutrition log for {log_date}. {len(meals)} item(s) today."


def _get_nutrition_log(user_id: str, inputs: dict) -> str:
    table    = db.get_table(NUTRITION_TABLE)
    log_date = inputs.get("date") or inputs.get("_today") or date.today().isoformat()
    existing = table.get_item(Key={"user_id": user_id, "log_date": log_date}).get("Item")
    if not existing or not existing.get("meals"):
        return f"No nutrition log for {log_date}."
    meals = existing["meals"]
    total_cal   = sum(m.get("calories",  0) or 0 for m in meals)
    total_prot  = sum(m.get("protein_g", 0) or 0 for m in meals)
    total_carbs = sum(m.get("carbs_g",   0) or 0 for m in meals)
    total_fat   = sum(m.get("fat_g",     0) or 0 for m in meals)
    lines = [f"Nutrition log for {log_date}:"]
    for m in meals:
        parts = []
        if m.get("calories"):  parts.append(f"{int(m['calories'])} cal")
        if m.get("protein_g"): parts.append(f"{m['protein_g']}g protein")
        lines.append(f"- {m['name']}" + (f" ({', '.join(parts)})" if parts else ""))
    lines.append(f"Totals: {int(total_cal)} cal · {total_prot}g protein · {total_carbs}g carbs · {total_fat}g fat")
    return "\n".join(lines)


def _log_exercise(user_id: str, inputs: dict) -> str:
    table    = db.get_table(HEALTH_TABLE)
    log_date = inputs.get("date") or inputs.get("_today") or date.today().isoformat()
    existing  = table.get_item(Key={"user_id": user_id, "log_date": log_date}).get("Item")
    exercises = list(existing.get("exercises", [])) if existing else []

    exercise = {"id": str(uuid.uuid4()), "name": inputs["name"].strip(), "sets": []}
    if inputs.get("duration_min") is not None:
        exercise["duration_min"] = Decimal(str(inputs["duration_min"]))
    if inputs.get("sets"):
        exercise["sets"] = [
            {k: Decimal(str(v)) if isinstance(v, (int, float)) else v for k, v in s.items()}
            for s in inputs["sets"]
        ]
    exercises.append(exercise)

    table.put_item(Item={
        "user_id":    user_id,
        "log_date":   log_date,
        "exercises":  exercises,
        "notes":      existing.get("notes", "") if existing else "",
        "created_at": existing["created_at"] if existing else _now(),
        "updated_at": _now(),
    })
    dur_str = f" ({int(exercise['duration_min'])} min)" if exercise.get("duration_min") else ""
    sets_str = f" — {len(exercise['sets'])} set(s)" if exercise.get("sets") else ""
    return f"Logged '{exercise['name']}'{dur_str}{sets_str} to exercise log for {log_date}. {len(exercises)} exercise(s) today."


def _get_exercise_log(user_id: str, inputs: dict) -> str:
    table    = db.get_table(HEALTH_TABLE)
    log_date = inputs.get("date") or inputs.get("_today") or date.today().isoformat()
    existing  = table.get_item(Key={"user_id": user_id, "log_date": log_date}).get("Item")
    if not existing or not existing.get("exercises"):
        return f"No exercise log for {log_date}."
    exercises = existing["exercises"]
    lines = [f"Exercise log for {log_date}:"]
    for ex in exercises:
        parts = []
        if ex.get("duration_min"): parts.append(f"{int(ex['duration_min'])} min")
        if ex.get("sets"):
            set_strs = [f"{s.get('reps', '?')} reps" + (f" @ {s['weight']} lbs" if s.get("weight") else "") for s in ex["sets"]]
            parts.append(", ".join(set_strs))
        lines.append(f"- {ex.get('name', 'Unnamed')}" + (f" ({'; '.join(parts)})" if parts else ""))
    return "\n".join(lines)


def _usda_search(food_name: str, data_types: str) -> list:
    params = urllib.parse.urlencode({
        "query":    food_name,
        "api_key":  os.environ.get("USDA_API_KEY", ""),
        "pageSize": 5,
        "dataType": data_types,
    })
    url = f"https://api.nal.usda.gov/fdc/v1/foods/search?{params}"
    with urllib.request.urlopen(url, timeout=6) as resp:  # nosec B310 — scheme hardcoded as https
        return json.loads(resp.read()).get("foods", [])


def _pick_usda_result(foods: list):
    """Return (food, nutrients_dict) for the first result with sane kcal (0–900/100g)."""
    for f in foods:
        nutrients = {}
        for item in f.get("foodNutrients", []):
            name = item["nutrientName"]
            val  = item.get("value", 0)
            unit = item.get("unitName", "")
            if name == "Energy":
                if unit == "KCAL":
                    nutrients["Energy"] = val
            else:
                nutrients[name] = val
        if 0 < nutrients.get("Energy", 0) <= 900:
            return f, nutrients
    return None, {}


def _lookup_nutrition(user_id: str, inputs: dict) -> str:
    food_name = inputs.get("food_name", "").strip()
    if not food_name:
        return "No food name provided."
    try:
        # Branded first (has real serving sizes from product labels)
        foods = _usda_search(food_name, "Branded")
        chosen, nutrients = _pick_usda_result(foods)
        # Fall back to Foundation/SR Legacy for generic foods
        if chosen is None:
            foods = _usda_search(food_name, "Foundation,SR Legacy")
            chosen, nutrients = _pick_usda_result(foods)
    except Exception as e:
        logger.warning("USDA lookup failed for '%s': %s", food_name, e)
        return f"Nutrition lookup unavailable. Use your general knowledge to estimate values for '{food_name}'."

    if chosen is None:
        return f"No reliable nutrition data found for '{food_name}'. Use your general knowledge to estimate."

    cal  = nutrients.get("Energy", 0)
    prot = nutrients.get("Protein", 0)
    carb = nutrients.get("Carbohydrate, by difference", 0)
    fat  = nutrients.get("Total lipid (fat)", 0)
    srv_g    = chosen.get("servingSize")
    srv_unit = chosen.get("servingSizeUnit", "g")
    name     = chosen.get("description", food_name)
    brand    = chosen.get("brandOwner", "")

    lines = [
        f"USDA data for: {name}" + (f" ({brand})" if brand else ""),
        f"Per 100g: {cal:.0f} cal | {prot:.1f}g protein | {carb:.1f}g carbs | {fat:.1f}g fat",
    ]
    if srv_g and str(srv_unit).upper() == "G":
        try:
            sq = float(srv_g)
            lines.append(
                f"Per labeled serving ({sq:.0f}g): "
                f"{cal*sq/100:.0f} cal | {prot*sq/100:.1f}g protein | "
                f"{carb*sq/100:.1f}g carbs | {fat*sq/100:.1f}g fat"
            )
        except (ValueError, TypeError):
            pass
    lines.append("Scale these values to the user's actual serving size, then call log_meal. When uncertain about exact weight, round calories UP — overestimating is better than underestimating for nutrition tracking.")
    return "\n".join(lines)


def _remember_fact(user_id: str, inputs: dict) -> str:
    mem.save_memory(user_id, inputs["key"], inputs["value"])
    return f"Remembered: {inputs['key']} = {inputs['value']}"
