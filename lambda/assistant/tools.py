"""Bedrock tool definitions and handlers for the AI assistant."""

import os
import uuid
from datetime import date, datetime, timezone

import db
import memory as mem

# ── Table env vars ────────────────────────────────────────────────────────────

TASKS_TABLE        = os.environ["TASKS_TABLE"]
NOTES_TABLE        = os.environ["NOTES_TABLE"]
NOTE_FOLDERS_TABLE = os.environ["NOTE_FOLDERS_TABLE"]
HABITS_TABLE       = os.environ["HABITS_TABLE"]
GOALS_TABLE        = os.environ["GOALS_TABLE"]
JOURNAL_TABLE      = os.environ["JOURNAL_TABLE"]


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

def handle_tool(user_id: str, name: str, inputs: dict) -> str:
    handlers = {
        "create_task":          _create_task,
        "list_tasks":           _list_tasks,
        "create_note":          _create_note,
        "create_note_folder":   _create_note_folder,
        "list_note_folders":    _list_note_folders,
        "create_habit":         _create_habit,
        "list_habits":          _list_habits,
        "create_goal":          _create_goal,
        "list_goals":           _list_goals,
        "create_journal_entry": _create_journal_entry,
        "remember_fact":        _remember_fact,
    }
    handler = handlers.get(name)
    if not handler:
        return f"Unknown tool: {name}"
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
    return f"Created task: {task['title']}"


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

    lines = []
    for t in filtered[:20]:
        due  = f" (due {t['due_date']})" if t.get("due_date") else ""
        lines.append(f"- [{t.get('status', 'todo')}] {t['title']}{due}")
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
    return f"Created note: {note.get('title', '(untitled)')}{location}"


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
    return f"Created goal: {goal['title']}"


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


def _create_journal_entry(user_id: str, inputs: dict) -> str:
    table      = db.get_table(JOURNAL_TABLE)
    entry_date = date.today().isoformat()
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
    return f"{action} journal entry for {entry_date}"


def _remember_fact(user_id: str, inputs: dict) -> str:
    mem.save_memory(user_id, inputs["key"], inputs["value"])
    return f"Remembered: {inputs['key']} = {inputs['value']}"
