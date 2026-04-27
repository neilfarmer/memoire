"""Bedrock tool definitions and handlers for the AI assistant."""

import json
import logging
import os
import re
import urllib.parse
import urllib.request
import uuid
from decimal import Decimal
from datetime import date, datetime, timezone

import db
import memory as mem

logger = logging.getLogger(__name__)


# ── Write-tool result contracts ───────────────────────────────────────────────
# Creation tools must emit an id or pal-link tag in their result so the UI can
# render the correct link and downstream callers can verify the action actually
# happened. If a tool's result doesn't match its contract, something went wrong
# silently — treat it as a tool error so the model retries.
WRITE_TOOL_TAG_PATTERNS: dict[str, re.Pattern] = {
    "create_task":          re.compile(r"\[pal-link:task:[^\]]+\]"),
    "schedule_tasks":       re.compile(r"\[pal-link:task:[^\]]+\]|No tasks needed scheduling|Couldn't fit any tasks"),
    "create_note":          re.compile(r"\[pal-link:note:[^\]]+\]"),
    "create_goal":          re.compile(r"\[pal-link:goal:[^\]]+\]"),
    "create_journal_entry": re.compile(r"\[pal-link:journal:[^\]]+\]"),
    "create_debt":          re.compile(r"\[id:[^\]]+\]"),
    "create_income":        re.compile(r"\[id:[^\]]+\]"),
    "create_expense":       re.compile(r"\[id:[^\]]+\]"),
    "create_bookmark":      re.compile(r"\[id:[^\]]+\]"),
    "add_favorite":         re.compile(r"\[id:[^\]]+\]"),
    "add_feed":             re.compile(r"\[id:[^\]]+\]"),
}


def verify_tool_result(name: str, result: str) -> str | None:
    """Return None if the result meets the tool's contract, else an error message."""
    pattern = WRITE_TOOL_TAG_PATTERNS.get(name)
    if not pattern:
        return None
    if pattern.search(result or ""):
        return None
    truncated = (result or "")[:200].replace("\n", " ")
    return f"{name} did not return an id tag (expected to match {pattern.pattern}). Raw result: {truncated!r}"

# ── Table env vars ────────────────────────────────────────────────────────────

TASKS_TABLE        = os.environ["TASKS_TABLE"]
NOTES_TABLE        = os.environ["NOTES_TABLE"]
NOTE_FOLDERS_TABLE = os.environ["NOTE_FOLDERS_TABLE"]
HABITS_TABLE       = os.environ["HABITS_TABLE"]
GOALS_TABLE        = os.environ["GOALS_TABLE"]
JOURNAL_TABLE      = os.environ["JOURNAL_TABLE"]
HEALTH_TABLE       = os.environ["HEALTH_TABLE"]
DEBTS_TABLE        = os.environ.get("DEBTS_TABLE", "")
INCOME_TABLE       = os.environ.get("INCOME_TABLE", "")
EXPENSES_TABLE     = os.environ.get("EXPENSES_TABLE", "")
BOOKMARKS_TABLE    = os.environ.get("BOOKMARKS_TABLE", "")
FAVORITES_TABLE    = os.environ.get("FAVORITES_TABLE", "")
FEEDS_TABLE        = os.environ.get("FEEDS_TABLE", "")
FEEDS_READ_TABLE   = os.environ.get("FEEDS_READ_TABLE", "")
LINKS_TABLE        = os.environ.get("LINKS_TABLE", "")
SETTINGS_TABLE     = os.environ.get("SETTINGS_TABLE", "")


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
                        "tags":        {"type": "array", "items": {"type": "string"}, "description": "Optional tag list for grouping/filtering"},
                    },
                    "required": ["title"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "update_task",
            "description": (
                "Update an EXISTING task — use this to change the title, due date, priority, "
                "status, description, or tags of a task that already exists. If the user says "
                "'change', 'rename', 'reschedule', 'tag as', 'update', 'set due to', etc. about "
                "a task from this session OR a task they can see in their list, ALWAYS use "
                "update_task, NEVER create_task. If you don't know the task_id, call list_tasks "
                "first to find it."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "task_id":     {"type": "string", "description": "The task id (from list_tasks [id:...])."},
                        "title":       {"type": "string", "description": "New title (optional)"},
                        "description": {"type": "string", "description": "New description (optional)"},
                        "due_date":    {"type": "string", "description": "New due date YYYY-MM-DD (optional)"},
                        "priority":    {"type": "string", "enum": ["low", "medium", "high"]},
                        "status":      {"type": "string", "enum": ["todo", "in_progress", "done"]},
                        "tags":        {"type": "array", "items": {"type": "string"}, "description": "Replace tag list. Use [] to clear."},
                    },
                    "required": ["task_id"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "schedule_tasks",
            "description": (
                "Auto-schedule the user's unscheduled tasks into 30-minute slots inside "
                "their working hours. Greedy first-fit; respects existing blocks. "
                "Use this when the user asks to 'auto-schedule', 'plan my day', "
                "'fit these in', or 'schedule everything'."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "task_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional. Only schedule these task ids. Omit to schedule all unscheduled tasks.",
                        },
                        "horizon_days": {
                            "type": "integer",
                            "description": "How many days ahead to consider when finding free slots (default 14).",
                        },
                        "respect_priority": {
                            "type": "boolean",
                            "description": "If true (default), schedule high priority before low.",
                        },
                    },
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
            "name": "update_note",
            "description": (
                "Update an EXISTING note's title or body. If the user says 'rename that note', "
                "'edit the note', 'change the body', etc., use update_note, NEVER create_note."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "note_id": {"type": "string", "description": "The note id (from list_notes)."},
                        "title":   {"type": "string", "description": "New title (optional)"},
                        "body":    {"type": "string", "description": "New body (optional)"},
                    },
                    "required": ["note_id"],
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
            "name": "update_habit",
            "description": (
                "Update an EXISTING habit — rename it or change its time_of_day. If the user "
                "says 'rename that habit', 'change the time', etc., use update_habit, NEVER create_habit."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "habit_id":    {"type": "string", "description": "The habit id (from list_habits)."},
                        "name":        {"type": "string", "description": "New name (optional)"},
                        "time_of_day": {"type": "string", "enum": ["anytime", "morning", "afternoon", "evening"]},
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
                "Log one or more food items to the nutrition log for a given date (defaults to today). "
                "Use this — NOT create_journal_entry — for ANY food, meal, eating, calorie, "
                "macro, or diet tracking request. PREFER the 'items' array when logging multiple "
                "foods at once (e.g. a meal with several components) — one call logs the whole "
                "meal. Single-item fields (name, calories, ...) are kept for backward compatibility."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "description": "Batch of food items to log in one call. Use this for multi-item meals.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name":      {"type": "string", "description": "Food item name"},
                                    "calories":  {"type": "number", "description": "Calories (kcal)"},
                                    "protein_g": {"type": "number", "description": "Protein in grams"},
                                    "carbs_g":   {"type": "number", "description": "Carbohydrates in grams"},
                                    "fat_g":     {"type": "number", "description": "Fat in grams"},
                                },
                                "required": ["name"],
                            },
                        },
                        "name":      {"type": "string", "description": "Food item name (single-item mode)"},
                        "calories":  {"type": "number", "description": "Calories (kcal)"},
                        "protein_g": {"type": "number", "description": "Protein in grams"},
                        "carbs_g":   {"type": "number", "description": "Carbohydrates in grams"},
                        "fat_g":     {"type": "number", "description": "Fat in grams"},
                        "date":      {"type": "string", "description": "Date YYYY-MM-DD, defaults to today"},
                    },
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
                "run, swim, lift, or physical activity tracking request. "
                "PREFER calling search_recent_exercises first when the user says they are "
                "repeating a previous workout (e.g. 'same as last time', 'my usual run') — "
                "it returns prior sets/duration/distance you can re-use."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "name":         {"type": "string", "description": "Exercise name, e.g. 'Bench Press' or 'Morning run'"},
                        "type":         {"type": "string", "enum": ["strength", "cardio", "mobility"], "description": "Exercise type. Drives UI rendering."},
                        "duration_min": {"type": "number", "description": "Duration in minutes (for cardio or timed exercises)"},
                        "distance_km":  {"type": "number", "description": "Distance in km (for cardio)"},
                        "intensity":    {"type": "number", "description": "RPE 0-10 (rate of perceived exertion)"},
                        "muscle_groups": {
                            "type": "array",
                            "description": "Muscle groups worked, e.g. ['chest', 'triceps']",
                            "items": {"type": "string"},
                        },
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

    # ── Journal extras ─────────────────────────────────────────────────────
    {"toolSpec": {
        "name": "list_journal_entries",
        "description": "List recent journal entry dates (most recent first).",
        "inputSchema": {"json": {"type": "object", "properties": {
            "limit": {"type": "number", "description": "Max entries to return (default 10, max 30)"},
        }}},
    }},
    {"toolSpec": {
        "name": "get_journal_entry",
        "description": "Get a journal entry by date.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "date": {"type": "string", "description": "YYYY-MM-DD (defaults to today)"},
        }}},
    }},
    {"toolSpec": {
        "name": "delete_journal_entry",
        "description": "Permanently delete a journal entry for a date.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "date": {"type": "string", "description": "YYYY-MM-DD (required)"},
        }, "required": ["date"]}},
    }},

    # ── Goals update ───────────────────────────────────────────────────────
    {"toolSpec": {
        "name": "update_goal",
        "description": "Update an EXISTING goal's title, description, or target_date. Use update_goal_progress for just progress %.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "goal_id":     {"type": "string", "description": "Goal id from list_goals"},
            "title":       {"type": "string"},
            "description": {"type": "string"},
            "target_date": {"type": "string", "description": "YYYY-MM-DD"},
        }, "required": ["goal_id"]}},
    }},

    # ── Nutrition delete ───────────────────────────────────────────────────
    {"toolSpec": {
        "name": "delete_meal",
        "description": "Remove a single meal item from a day's nutrition log.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "date":    {"type": "string", "description": "YYYY-MM-DD (defaults to today)"},
            "meal_id": {"type": "string", "description": "The meal id to remove"},
            "name":    {"type": "string", "description": "Alternatively match by name (first match wins)"},
        }}},
    }},
    {"toolSpec": {
        "name": "clear_nutrition_log",
        "description": "Clear all meals from a day's nutrition log.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "date": {"type": "string", "description": "YYYY-MM-DD (defaults to today)"},
        }}},
    }},

    # ── Exercise delete / list days ────────────────────────────────────────
    {"toolSpec": {
        "name": "delete_exercise",
        "description": "Remove a single exercise from a day's exercise log.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "date":        {"type": "string", "description": "YYYY-MM-DD (defaults to today)"},
            "exercise_id": {"type": "string"},
            "name":        {"type": "string", "description": "Alternatively match by name"},
        }}},
    }},
    {"toolSpec": {
        "name": "list_exercise_days",
        "description": "List recent dates that have exercise log entries.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "limit": {"type": "number", "description": "Max dates (default 7)"},
        }}},
    }},
    {"toolSpec": {
        "name": "search_recent_exercises",
        "description": (
            "Search recently logged exercises to re-use a previous workout. Returns distinct "
            "exercise names with their most recent sets/duration/distance/type. Call this "
            "BEFORE log_exercise when the user says 'same as last time', 'my usual run', "
            "'repeat yesterday's workout', etc — then copy the returned config into log_exercise."
        ),
        "inputSchema": {"json": {"type": "object", "properties": {
            "q":     {"type": "string", "description": "Optional substring filter on name (case-insensitive)"},
            "days":  {"type": "number", "description": "Look back this many days (default 90)"},
            "limit": {"type": "number", "description": "Max results (default 20)"},
        }}},
    }},
    {"toolSpec": {
        "name": "search_recent_meals",
        "description": (
            "Search recently eaten meals to re-log a previous entry. Returns distinct meal "
            "names with their most recent macros. Call this BEFORE log_meal when the user "
            "says 'same lunch as yesterday', 'my usual breakfast', etc — then copy the "
            "returned macros into log_meal."
        ),
        "inputSchema": {"json": {"type": "object", "properties": {
            "q":     {"type": "string", "description": "Optional substring filter on name (case-insensitive)"},
            "days":  {"type": "number", "description": "Look back this many days (default 90)"},
            "limit": {"type": "number", "description": "Max results (default 20)"},
        }}},
    }},
    {"toolSpec": {
        "name": "get_exercise_summary",
        "description": "Get rollup metrics (volume, duration, distance, workout days, streak) across a date range. Use when the user asks about weekly/monthly totals or trends.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "from": {"type": "string", "description": "YYYY-MM-DD (default: 30 days ago)"},
            "to":   {"type": "string", "description": "YYYY-MM-DD (default: today)"},
        }}},
    }},
    {"toolSpec": {
        "name": "get_nutrition_summary",
        "description": "Get rollup macros (totals, per-day averages, streak) across a date range. Use when the user asks about weekly/monthly totals or averages.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "from": {"type": "string", "description": "YYYY-MM-DD (default: 30 days ago)"},
            "to":   {"type": "string", "description": "YYYY-MM-DD (default: today)"},
        }}},
    }},

    # ── Health ─────────────────────────────────────────────────────────────
    {"toolSpec": {
        "name": "log_health",
        "description": "Record daily health metrics (weight, sleep hours, mood) for a date.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "date":         {"type": "string", "description": "YYYY-MM-DD (defaults to today)"},
            "weight":       {"type": "number", "description": "Weight (user's unit of choice)"},
            "sleep_hours":  {"type": "number"},
            "mood":         {"type": "string", "enum": ["great", "good", "okay", "bad", "terrible"]},
            "notes":        {"type": "string"},
        }}},
    }},
    {"toolSpec": {
        "name": "get_health_log",
        "description": "Get health metrics for a date.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "date": {"type": "string", "description": "YYYY-MM-DD"},
        }}},
    }},
    {"toolSpec": {
        "name": "list_health_logs",
        "description": "List recent health log dates.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "limit": {"type": "number"},
        }}},
    }},
    {"toolSpec": {
        "name": "delete_health_log",
        "description": "Delete the health log for a date.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "date": {"type": "string"},
        }, "required": ["date"]}},
    }},

    # ── Finances ───────────────────────────────────────────────────────────
    {"toolSpec": {
        "name": "list_debts",
        "description": "List the user's debts (credit cards, loans, etc.).",
        "inputSchema": {"json": {"type": "object", "properties": {}}},
    }},
    {"toolSpec": {
        "name": "create_debt",
        "description": "Record a new debt.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "name":       {"type": "string"},
            "balance":    {"type": "number"},
            "apr":        {"type": "number", "description": "Annual percentage rate (e.g. 18.99)"},
            "min_payment": {"type": "number"},
        }, "required": ["name", "balance"]}},
    }},
    {"toolSpec": {
        "name": "update_debt",
        "description": "Update an existing debt by id.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "debt_id":    {"type": "string"},
            "name":       {"type": "string"},
            "balance":    {"type": "number"},
            "apr":        {"type": "number"},
            "min_payment": {"type": "number"},
        }, "required": ["debt_id"]}},
    }},
    {"toolSpec": {
        "name": "delete_debt",
        "description": "Delete a debt by id.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "debt_id": {"type": "string"},
        }, "required": ["debt_id"]}},
    }},
    {"toolSpec": {
        "name": "list_income",
        "description": "List the user's income sources.",
        "inputSchema": {"json": {"type": "object", "properties": {}}},
    }},
    {"toolSpec": {
        "name": "create_income",
        "description": "Record a new income source.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "name":      {"type": "string"},
            "amount":    {"type": "number"},
            "frequency": {"type": "string", "enum": ["weekly", "biweekly", "monthly", "yearly"]},
        }, "required": ["name", "amount"]}},
    }},
    {"toolSpec": {
        "name": "update_income",
        "description": "Update an income source by id.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "income_id": {"type": "string"},
            "name":      {"type": "string"},
            "amount":    {"type": "number"},
            "frequency": {"type": "string", "enum": ["weekly", "biweekly", "monthly", "yearly"]},
        }, "required": ["income_id"]}},
    }},
    {"toolSpec": {
        "name": "delete_income",
        "description": "Delete an income source by id.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "income_id": {"type": "string"},
        }, "required": ["income_id"]}},
    }},
    {"toolSpec": {
        "name": "list_expenses",
        "description": "List fixed recurring expenses.",
        "inputSchema": {"json": {"type": "object", "properties": {}}},
    }},
    {"toolSpec": {
        "name": "create_expense",
        "description": "Record a new fixed expense.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "name":      {"type": "string"},
            "amount":    {"type": "number"},
            "frequency": {"type": "string", "enum": ["weekly", "biweekly", "monthly", "yearly"]},
            "due_day":   {"type": "number", "description": "Day of month (1-31) for monthly bills"},
        }, "required": ["name", "amount"]}},
    }},
    {"toolSpec": {
        "name": "update_expense",
        "description": "Update a fixed expense by id.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "expense_id": {"type": "string"},
            "name":       {"type": "string"},
            "amount":     {"type": "number"},
            "frequency":  {"type": "string", "enum": ["weekly", "biweekly", "monthly", "yearly"]},
            "due_day":    {"type": "number"},
        }, "required": ["expense_id"]}},
    }},
    {"toolSpec": {
        "name": "delete_expense",
        "description": "Delete a fixed expense by id.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "expense_id": {"type": "string"},
        }, "required": ["expense_id"]}},
    }},
    {"toolSpec": {
        "name": "get_finances_summary",
        "description": "Summary of income, expenses, debts, and net cash flow.",
        "inputSchema": {"json": {"type": "object", "properties": {}}},
    }},

    # ── Bookmarks ──────────────────────────────────────────────────────────
    {"toolSpec": {
        "name": "create_bookmark",
        "description": "Save a URL as a bookmark.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "url":         {"type": "string"},
            "title":       {"type": "string"},
            "description": {"type": "string"},
            "tags":        {"type": "array", "items": {"type": "string"}},
        }, "required": ["url"]}},
    }},
    {"toolSpec": {
        "name": "list_bookmarks",
        "description": "List the user's bookmarks.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "tag": {"type": "string", "description": "Filter by tag"},
        }}},
    }},
    {"toolSpec": {
        "name": "update_bookmark",
        "description": "Update a bookmark by id.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "bookmark_id": {"type": "string"},
            "title":       {"type": "string"},
            "description": {"type": "string"},
            "tags":        {"type": "array", "items": {"type": "string"}},
        }, "required": ["bookmark_id"]}},
    }},
    {"toolSpec": {
        "name": "delete_bookmark",
        "description": "Delete a bookmark by id.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "bookmark_id": {"type": "string"},
        }, "required": ["bookmark_id"]}},
    }},

    # ── Favorites ──────────────────────────────────────────────────────────
    {"toolSpec": {
        "name": "add_favorite",
        "description": "Mark an item (task/note/goal/etc.) as a favorite.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "kind":    {"type": "string", "description": "Type of thing: task, note, goal, bookmark, etc."},
            "item_id": {"type": "string"},
            "label":   {"type": "string", "description": "Display label"},
            "tags":    {"type": "array", "items": {"type": "string"}},
        }, "required": ["kind", "item_id"]}},
    }},
    {"toolSpec": {
        "name": "list_favorites",
        "description": "List the user's favorites.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "kind": {"type": "string", "description": "Filter by kind"},
        }}},
    }},
    {"toolSpec": {
        "name": "remove_favorite",
        "description": "Remove a favorite by id.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "favorite_id": {"type": "string"},
        }, "required": ["favorite_id"]}},
    }},

    # ── Feeds ──────────────────────────────────────────────────────────────
    {"toolSpec": {
        "name": "list_feeds",
        "description": "List the user's RSS feed subscriptions.",
        "inputSchema": {"json": {"type": "object", "properties": {}}},
    }},
    {"toolSpec": {
        "name": "add_feed",
        "description": "Subscribe to an RSS feed URL.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "url":  {"type": "string"},
            "name": {"type": "string"},
        }, "required": ["url"]}},
    }},
    {"toolSpec": {
        "name": "delete_feed",
        "description": "Unsubscribe from a feed.",
        "inputSchema": {"json": {"type": "object", "properties": {
            "feed_id": {"type": "string"},
        }, "required": ["feed_id"]}},
    }},

    # ── Links graph ────────────────────────────────────────────────────────
    {"toolSpec": {
        "name": "get_links",
        "description": (
            "Traverse the wiki-link graph for an entity. Notes, journal "
            "entries, and tasks may reference other items via [[type:id]] "
            "tags in their body. Use this tool to fetch outbound references "
            "(what this entity links to), inbound backlinks (what links to "
            "this entity), or both. Useful for cross-feature questions "
            "like 'what notes mention this task?'."
        ),
        "inputSchema": {"json": {"type": "object", "properties": {
            "entity_type": {
                "type": "string",
                "description": "Type of the entity, e.g. note, task, journal, goal, habit, bookmark.",
            },
            "entity_id": {
                "type": "string",
                "description": "Id of the entity (for journal, the YYYY-MM-DD date).",
            },
            "direction": {
                "type": "string",
                "enum": ["outbound", "inbound", "both"],
                "description": "outbound = links this entity emits; inbound = links pointing at it. Defaults to both.",
            },
        }, "required": ["entity_type", "entity_id"]}},
    }},
]


# ── Tool handlers ─────────────────────────────────────────────────────────────

def handle_tool(user_id: str, name: str, inputs: dict, local_date: str | None = None) -> str:
    _today = local_date or date.today().isoformat()
    handlers = {
        "create_task":          _create_task,
        "update_task":          _update_task,
        "list_tasks":           _list_tasks,
        "schedule_tasks":       _schedule_tasks,
        "complete_task":        _complete_task,
        "delete_task":          _delete_task,
        "create_note":          _create_note,
        "update_note":          _update_note,
        "list_notes":           _list_notes,
        "delete_note":          _delete_note,
        "create_note_folder":   _create_note_folder,
        "list_note_folders":    _list_note_folders,
        "create_habit":         _create_habit,
        "update_habit":         _update_habit,
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
        # Journal extras
        "list_journal_entries": _list_journal_entries,
        "get_journal_entry":    _get_journal_entry,
        "delete_journal_entry": _delete_journal_entry,
        # Goals
        "update_goal":          _update_goal,
        # Nutrition delete
        "delete_meal":          _delete_meal,
        "clear_nutrition_log":  _clear_nutrition_log,
        # Exercise extras
        "delete_exercise":      _delete_exercise,
        "list_exercise_days":   _list_exercise_days,
        "search_recent_exercises": _search_recent_exercises,
        "search_recent_meals":  _search_recent_meals,
        "get_exercise_summary": _get_exercise_summary,
        "get_nutrition_summary": _get_nutrition_summary,
        # Health
        "log_health":           _log_health,
        "get_health_log":       _get_health_log,
        "list_health_logs":     _list_health_logs,
        "delete_health_log":    _delete_health_log,
        # Finances
        "list_debts":           _list_debts,
        "create_debt":          _create_debt,
        "update_debt":          _update_debt,
        "delete_debt":          _delete_debt,
        "list_income":          _list_income,
        "create_income":        _create_income,
        "update_income":        _update_income,
        "delete_income":        _delete_income,
        "list_expenses":        _list_expenses,
        "create_expense":       _create_expense,
        "update_expense":       _update_expense,
        "delete_expense":       _delete_expense,
        "get_finances_summary": _get_finances_summary,
        # Bookmarks
        "create_bookmark":      _create_bookmark,
        "list_bookmarks":       _list_bookmarks,
        "update_bookmark":      _update_bookmark,
        "delete_bookmark":      _delete_bookmark,
        # Favorites
        "add_favorite":         _add_favorite,
        "list_favorites":       _list_favorites,
        "remove_favorite":      _remove_favorite,
        # Feeds
        "list_feeds":           _list_feeds,
        "add_feed":             _add_feed,
        "delete_feed":          _delete_feed,
        # Links graph
        "get_links":            _get_links,
    }
    handler = handlers.get(name)
    if not handler:
        return f"Unknown tool: {name}"
    # Inject local today for tools that default to "today"
    _date_aware = {"log_meal", "get_nutrition_log", "log_exercise", "get_exercise_log",
                   "create_journal_entry", "toggle_habit",
                   "delete_meal", "clear_nutrition_log", "delete_exercise",
                   "log_health", "get_health_log",
                   "list_journal_entries", "get_journal_entry"}
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
        "tags":       _normalize_tag_input(inputs.get("tags")),
        "created_at": now,
        "updated_at": now,
    }
    if inputs.get("due_date"):
        task["due_date"] = inputs["due_date"]
    task = {k: v for k, v in task.items() if v is not None and v != ""}
    table.put_item(Item=task)
    return f"Created task: {task['title']} [pal-link:task:{task['task_id']}:Open task →]"


def _normalize_tag_input(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [t for t in raw.split(",")]
    if not isinstance(raw, list):
        return []
    seen, out = set(), []
    for tag in raw:
        if not isinstance(tag, str):
            continue
        norm = tag.strip()
        if not norm or norm.lower() in seen:
            continue
        seen.add(norm.lower())
        out.append(norm)
    return out


def _schedule_tasks(user_id: str, inputs: dict) -> str:
    import scheduler  # shared layer

    table = db.get_table(TASKS_TABLE)
    settings_item = {}
    if SETTINGS_TABLE:
        settings_item = (
            db.get_table(SETTINGS_TABLE).get_item(Key={"user_id": user_id}).get("Item") or {}
        )
    cal = scheduler._coerce_calendar(settings_item)
    horizon = inputs.get("horizon_days")
    if isinstance(horizon, int) and horizon > 0:
        cal["horizon_days"] = min(horizon, 60)

    tz = scheduler._zone(cal["timezone"])
    now = datetime.now(timezone.utc)

    requested_ids = set(inputs.get("task_ids") or [])
    all_tasks = db.query_by_user(table, user_id)

    if requested_ids:
        targets = [t for t in all_tasks if t.get("task_id") in requested_ids]
    else:
        targets = [t for t in all_tasks
                   if t.get("status") in ("todo", "in_progress")
                   and not t.get("scheduled_start")
                   and not t.get("recurrence_rule")]

    if not targets:
        return "No tasks needed scheduling."

    priority_rank = {"high": 0, "medium": 1, "low": 2}
    if inputs.get("respect_priority", True):
        targets.sort(key=lambda t: (
            priority_rank.get(t.get("priority", "medium"), 1),
            t.get("due_date") or "9999-12-31",
            t.get("created_at") or "",
        ))

    busy = scheduler._busy_intervals(all_tasks)
    scheduled, skipped = [], []

    for task in targets:
        try:
            duration = int(task.get("duration_minutes") or cal["slot_minutes"])
        except (TypeError, ValueError):
            duration = cal["slot_minutes"]
        slot = scheduler._find_free_slot(now, duration, cal, tz, busy,
                                         exclude_id=task.get("task_id"))
        if not slot:
            skipped.append(task.get("title", task.get("task_id", "")))
            continue
        table.update_item(
            Key={"user_id": user_id, "task_id": task["task_id"]},
            UpdateExpression="SET scheduled_start = :s, duration_minutes = :d, updated_at = :u",
            ExpressionAttributeValues={
                ":s": slot.isoformat(),
                ":d": duration,
                ":u": now.isoformat(),
            },
        )
        busy.append((slot.timestamp(), slot.timestamp() + duration * 60, task["task_id"]))
        scheduled.append((task, slot))

    if not scheduled:
        return f"Couldn't fit any tasks into your schedule. Skipped: {len(skipped)}"

    lines = [f"Scheduled {len(scheduled)} task(s):"]
    for task, slot in scheduled:
        local = slot.astimezone(tz).strftime("%a %b %d %H:%M")
        lines.append(f"- {task.get('title', '')} at {local} [pal-link:task:{task['task_id']}]")
    if skipped:
        lines.append(f"Skipped {len(skipped)} (no free slot).")
    return "\n".join(lines)


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


def _update_task(user_id: str, inputs: dict) -> str:
    table   = db.get_table(TASKS_TABLE)
    task_id = inputs["task_id"]
    existing = db.get_item(table, user_id, "task_id", task_id)
    if not existing:
        return f"Task {task_id} not found."

    fields = {}
    for k in ("title", "description", "due_date", "priority", "status"):
        if k in inputs and inputs[k] is not None and inputs[k] != "":
            fields[k] = inputs[k]
    if "tags" in inputs and inputs["tags"] is not None:
        fields["tags"] = _normalize_tag_input(inputs["tags"])
    if not fields:
        return "No fields supplied to update."

    if "title" in fields:
        fields["title"] = fields["title"].strip()
        if not fields["title"]:
            return "title cannot be empty."

    fields["updated_at"] = _now()
    set_parts = []
    names  = {}
    values = {}
    for i, (k, v) in enumerate(fields.items()):
        names[f"#k{i}"]  = k
        values[f":v{i}"] = v
        set_parts.append(f"#k{i} = :v{i}")
    table.update_item(
        Key={"user_id": user_id, "task_id": task_id},
        UpdateExpression="SET " + ", ".join(set_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )
    changed = ", ".join(f"{k}={v}" for k, v in fields.items() if k != "updated_at")
    return (
        f"Updated task '{existing.get('title', task_id)}': {changed} "
        f"[pal-link:task:{task_id}:Open task →]"
    )


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


def _update_note(user_id: str, inputs: dict) -> str:
    table   = db.get_table(NOTES_TABLE)
    note_id = inputs["note_id"]
    existing = db.get_item(table, user_id, "note_id", note_id)
    if not existing:
        return f"Note {note_id} not found."

    fields = {}
    if inputs.get("title"):
        fields["title"] = inputs["title"].strip()
    if "body" in inputs and inputs["body"] is not None:
        fields["body"] = inputs["body"]
    if not fields:
        return "No fields supplied to update."
    fields["updated_at"] = _now()

    set_parts, names, values = [], {}, {}
    for i, (k, v) in enumerate(fields.items()):
        names[f"#k{i}"]  = k
        values[f":v{i}"] = v
        set_parts.append(f"#k{i} = :v{i}")
    table.update_item(
        Key={"user_id": user_id, "note_id": note_id},
        UpdateExpression="SET " + ", ".join(set_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )
    changed = ", ".join(f"{k}" for k in fields if k != "updated_at")
    return f"Updated note '{fields.get('title', existing.get('title', note_id))}': {changed}"


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


def _update_habit(user_id: str, inputs: dict) -> str:
    table    = db.get_table(HABITS_TABLE)
    habit_id = inputs["habit_id"]
    existing = db.get_item(table, user_id, "habit_id", habit_id)
    if not existing:
        return f"Habit {habit_id} not found."

    fields = {}
    if inputs.get("name"):
        fields["name"] = inputs["name"].strip()
    if inputs.get("time_of_day"):
        fields["time_of_day"] = inputs["time_of_day"]
    if not fields:
        return "No fields supplied to update."
    fields["updated_at"] = _now()

    set_parts, names, values = [], {}, {}
    for i, (k, v) in enumerate(fields.items()):
        names[f"#k{i}"]  = k
        values[f":v{i}"] = v
        set_parts.append(f"#k{i} = :v{i}")
    table.update_item(
        Key={"user_id": user_id, "habit_id": habit_id},
        UpdateExpression="SET " + ", ".join(set_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )
    changed = ", ".join(f"{k}={v}" for k, v in fields.items() if k != "updated_at")
    return f"Updated habit '{fields.get('name', existing.get('name', habit_id))}': {changed}"


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
    table    = db.get_table(HEALTH_TABLE)
    log_date = inputs.get("date") or inputs.get("_today") or date.today().isoformat()
    existing = table.get_item(Key={"user_id": user_id, "log_date": log_date}).get("Item") or {}
    foods    = list(existing.get("foods", []))

    raw_items = inputs.get("items")
    if raw_items and isinstance(raw_items, list):
        new_items = raw_items
    elif inputs.get("name"):
        new_items = [{k: inputs.get(k) for k in ("name", "calories", "protein_g", "carbs_g", "fat_g")}]
    else:
        return "log_meal requires either 'items' (array) or 'name' (single item)."

    added_names = []
    added_cals  = 0
    for src in new_items:
        name = (src.get("name") or "").strip()
        if not name:
            continue
        food = {"id": str(uuid.uuid4()), "name": name, "source": "assistant"}
        for field in ("calories", "protein_g", "carbs_g", "fat_g"):
            if src.get(field) is not None:
                food[field] = Decimal(str(src[field]))
        foods.append(food)
        added_names.append(name)
        if food.get("calories"):
            added_cals += int(food["calories"])

    if not added_names:
        return "No valid items supplied to log_meal."

    table.put_item(Item={
        **existing,
        "user_id":    user_id,
        "log_date":   log_date,
        "foods":      foods,
        "exercises":  list(existing.get("exercises", [])),
        "notes":      existing.get("notes", ""),
        "created_at": existing.get("created_at") or _now(),
        "updated_at": _now(),
    })

    if len(added_names) == 1:
        cal_str = f" ({added_cals} cal)" if added_cals else ""
        return f"Logged '{added_names[0]}'{cal_str} to health log for {log_date}. {len(foods)} item(s) today."
    cal_str = f" ({added_cals} cal total)" if added_cals else ""
    return f"Logged {len(added_names)} items{cal_str} to health log for {log_date}: {', '.join(added_names)}. {len(foods)} item(s) today."


def _get_nutrition_log(user_id: str, inputs: dict) -> str:
    table    = db.get_table(HEALTH_TABLE)
    log_date = inputs.get("date") or inputs.get("_today") or date.today().isoformat()
    existing = table.get_item(Key={"user_id": user_id, "log_date": log_date}).get("Item")
    if not existing or not existing.get("foods"):
        return f"No nutrition log for {log_date}."
    foods = existing["foods"]
    total_cal   = sum(m.get("calories",  0) or 0 for m in foods)
    total_prot  = sum(m.get("protein_g", 0) or 0 for m in foods)
    total_carbs = sum(m.get("carbs_g",   0) or 0 for m in foods)
    total_fat   = sum(m.get("fat_g",     0) or 0 for m in foods)
    lines = [f"Nutrition log for {log_date}:"]
    for m in foods:
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
    if inputs.get("type") in ("strength", "cardio", "mobility"):
        exercise["type"] = inputs["type"]
    if inputs.get("duration_min") is not None:
        exercise["duration_min"] = Decimal(str(inputs["duration_min"]))
    if inputs.get("distance_km") is not None:
        exercise["distance_km"] = Decimal(str(inputs["distance_km"]))
    if inputs.get("intensity") is not None:
        exercise["intensity"] = Decimal(str(inputs["intensity"]))
    if isinstance(inputs.get("muscle_groups"), list):
        exercise["muscle_groups"] = [str(m).strip() for m in inputs["muscle_groups"] if str(m).strip()]
    if inputs.get("sets"):
        exercise["sets"] = [
            {k: Decimal(str(v)) if isinstance(v, (int, float)) else v for k, v in s.items()}
            for s in inputs["sets"]
        ]
    exercises.append(exercise)

    table.put_item(Item={
        **(existing or {}),
        "user_id":    user_id,
        "log_date":   log_date,
        "exercises":  exercises,
        "foods":      list((existing or {}).get("foods", [])),
        "notes":      (existing or {}).get("notes", ""),
        "created_at": (existing or {}).get("created_at") or _now(),
        "updated_at": _now(),
    })
    dur_str = f" ({int(exercise['duration_min'])} min)" if exercise.get("duration_min") else ""
    sets_str = f" — {len(exercise['sets'])} set(s)" if exercise.get("sets") else ""
    return f"Logged '{exercise['name']}'{dur_str}{sets_str} to exercise log for {log_date}. {len(exercises)} exercise(s) today."


def _search_recent_exercises(user_id: str, inputs: dict) -> str:
    from datetime import timedelta
    table   = db.get_table(HEALTH_TABLE)
    q       = (inputs.get("q") or "").strip().lower()
    days    = max(1, min(int(inputs.get("days") or 90), 365))
    limit   = max(1, min(int(inputs.get("limit") or 20), 100))
    cutoff  = (date.today() - timedelta(days=days)).isoformat()
    items   = [i for i in db.query_by_user(table, user_id) if i.get("log_date", "") >= cutoff]
    items.sort(key=lambda x: x["log_date"], reverse=True)

    seen: dict[str, dict] = {}
    for item in items:
        for ex in item.get("exercises") or []:
            name = (ex.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            if q and q not in key:
                continue
            if key in seen:
                seen[key]["count"] += 1
                continue
            seen[key] = {
                "name": name, "last_date": item["log_date"], "count": 1,
                "type": ex.get("type"), "sets": ex.get("sets") or [],
                "duration_min": ex.get("duration_min"),
                "distance_km": ex.get("distance_km"),
                "muscle_groups": ex.get("muscle_groups") or [],
            }

    results = list(seen.values())[:limit]
    if not results:
        return f"No matching exercises in the last {days} days."
    lines = [f"Recent exercises ({'matching ' + chr(39) + q + chr(39) + ', ' if q else ''}last {days} days):"]
    for r in results:
        parts = [f"last {r['last_date']}", f"{r['count']}x"]
        if r.get("type"):          parts.append(r["type"])
        if r.get("sets"):
            sets_s = ", ".join(f"{s.get('reps','?')}x{s.get('weight','?')}" for s in r["sets"])
            parts.append(f"sets: {sets_s}")
        if r.get("duration_min") is not None: parts.append(f"{int(r['duration_min'])} min")
        if r.get("distance_km")  is not None: parts.append(f"{r['distance_km']} km")
        lines.append(f"- {r['name']} ({'; '.join(parts)})")
    return "\n".join(lines)


def _search_recent_meals(user_id: str, inputs: dict) -> str:
    from datetime import timedelta
    table   = db.get_table(HEALTH_TABLE)
    q       = (inputs.get("q") or "").strip().lower()
    days    = max(1, min(int(inputs.get("days") or 90), 365))
    limit   = max(1, min(int(inputs.get("limit") or 20), 100))
    cutoff  = (date.today() - timedelta(days=days)).isoformat()
    items   = [i for i in db.query_by_user(table, user_id) if i.get("log_date", "") >= cutoff]
    items.sort(key=lambda x: x["log_date"], reverse=True)

    seen: dict[str, dict] = {}
    for item in items:
        for m in item.get("foods") or []:
            name = (m.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            if q and q not in key:
                continue
            if key in seen:
                seen[key]["count"] += 1
                continue
            entry = {"name": name, "last_date": item["log_date"], "count": 1}
            for f in ("calories", "protein_g", "carbs_g", "fat_g"):
                if m.get(f) is not None:
                    entry[f] = m[f]
            seen[key] = entry

    results = list(seen.values())[:limit]
    if not results:
        return f"No matching meals in the last {days} days."
    lines = [f"Recent meals ({'matching ' + chr(39) + q + chr(39) + ', ' if q else ''}last {days} days):"]
    for r in results:
        parts = [f"last {r['last_date']}", f"{r['count']}x"]
        if r.get("calories") is not None:
            macros = f"{int(r['calories'])} cal"
            if r.get("protein_g") is not None: macros += f", {r['protein_g']}P"
            if r.get("carbs_g")   is not None: macros += f"/{r['carbs_g']}C"
            if r.get("fat_g")     is not None: macros += f"/{r['fat_g']}F"
            parts.append(macros)
        lines.append(f"- {r['name']} ({'; '.join(parts)})")
    return "\n".join(lines)


def _get_exercise_summary(user_id: str, inputs: dict) -> str:
    from datetime import timedelta
    table = db.get_table(HEALTH_TABLE)
    today = date.today()
    d_to   = inputs.get("to")   or today.isoformat()
    d_from = inputs.get("from") or (today - timedelta(days=29)).isoformat()
    items  = [i for i in db.query_by_user(table, user_id) if d_from <= i.get("log_date", "") <= d_to]

    total_vol  = Decimal("0")
    total_dur  = Decimal("0")
    total_dist = Decimal("0")
    workout_days = 0
    ex_count = 0
    for item in items:
        ex_list = item.get("exercises") or []
        if not ex_list:
            continue
        workout_days += 1
        ex_count += len(ex_list)
        for ex in ex_list:
            if ex.get("duration_min") is not None: total_dur += Decimal(str(ex["duration_min"]))
            if ex.get("distance_km")  is not None: total_dist += Decimal(str(ex["distance_km"]))
            for s in ex.get("sets") or []:
                if s.get("reps") is not None and s.get("weight") is not None:
                    total_vol += Decimal(str(s["reps"])) * Decimal(str(s["weight"]))

    lines = [f"Exercise summary {d_from} to {d_to}:",
             f"- {workout_days} workout day(s), {ex_count} exercise(s)"]
    if total_vol:  lines.append(f"- Total volume: {int(total_vol)} lbs")
    if total_dur:  lines.append(f"- Total duration: {int(total_dur)} min")
    if total_dist: lines.append(f"- Total distance: {total_dist} km")
    return "\n".join(lines)


def _get_nutrition_summary(user_id: str, inputs: dict) -> str:
    from datetime import timedelta
    table = db.get_table(HEALTH_TABLE)
    today = date.today()
    d_to   = inputs.get("to")   or today.isoformat()
    d_from = inputs.get("from") or (today - timedelta(days=29)).isoformat()
    items  = [i for i in db.query_by_user(table, user_id) if d_from <= i.get("log_date", "") <= d_to]

    totals = {f: Decimal("0") for f in ("calories", "protein_g", "carbs_g", "fat_g")}
    logged_days = 0
    meal_count = 0
    for item in items:
        foods = item.get("foods") or []
        if not foods:
            continue
        logged_days += 1
        meal_count += len(foods)
        for m in foods:
            for f in totals:
                if m.get(f) is not None:
                    totals[f] += Decimal(str(m[f]))

    lines = [f"Nutrition summary {d_from} to {d_to}:",
             f"- {logged_days} logged day(s), {meal_count} meal(s)"]
    if logged_days:
        avg_cal = int(totals["calories"] / logged_days)
        lines.append(f"- Avg/day: {avg_cal} cal, "
                     f"{int(totals['protein_g']/logged_days)}g P, "
                     f"{int(totals['carbs_g']/logged_days)}g C, "
                     f"{int(totals['fat_g']/logged_days)}g F")
    return "\n".join(lines)


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
    import facts as _fct
    key      = _fct.canonical_key(inputs["key"])
    new_val  = inputs["value"].strip()
    if not key or key.startswith("__") or not new_val:
        return "Skipped: empty fact."
    if _fct.looks_like_task(new_val):
        return "Skipped: looks like a task, not a durable fact."
    existing_facts, _ = mem.load_memory(user_id)
    existing = existing_facts.get(key, "")
    merged   = _fct.merge_values(existing, new_val)
    if not merged:
        return "Skipped: no useful content after cleanup."
    if merged == existing:
        return f"Already knew: {key} = {existing}"
    mem.save_memory(user_id, key, merged)
    return f"Remembered: {key} = {merged}"


# ── Journal extras ────────────────────────────────────────────────────────────

def _list_journal_entries(user_id: str, inputs: dict) -> str:
    table = db.get_table(JOURNAL_TABLE)
    items = db.query_by_user(table, user_id)
    items.sort(key=lambda x: x.get("entry_date", ""), reverse=True)
    limit = min(int(inputs.get("limit", 10) or 10), 30)
    items = items[:limit]
    if not items:
        return "No journal entries yet."
    lines = ["Journal entries:"]
    for e in items:
        d    = e.get("entry_date", "")
        mood = e.get("mood", "")
        body = (e.get("body", "") or "").strip().replace("\n", " ")
        preview = body[:80] + ("..." if len(body) > 80 else "")
        mood_str = f" [{mood}]" if mood else ""
        lines.append(f"- {d}{mood_str}: {preview} [pal-link:journal:{d}:Open →]")
    return "\n".join(lines)


def _get_journal_entry(user_id: str, inputs: dict) -> str:
    table = db.get_table(JOURNAL_TABLE)
    d     = inputs.get("date") or inputs.get("_today") or date.today().isoformat()
    item  = table.get_item(Key={"user_id": user_id, "entry_date": d}).get("Item")
    if not item:
        return f"No journal entry for {d}."
    mood = item.get("mood", "")
    body = item.get("body", "")
    return f"Journal {d}{' (' + mood + ')' if mood else ''}:\n{body}"


def _delete_journal_entry(user_id: str, inputs: dict) -> str:
    table = db.get_table(JOURNAL_TABLE)
    d     = inputs["date"]
    item  = table.get_item(Key={"user_id": user_id, "entry_date": d}).get("Item")
    if not item:
        return f"No journal entry for {d}."
    table.delete_item(Key={"user_id": user_id, "entry_date": d})
    return f"Deleted journal entry for {d}."


# ── Goals update ──────────────────────────────────────────────────────────────

def _update_goal(user_id: str, inputs: dict) -> str:
    table   = db.get_table(GOALS_TABLE)
    goal_id = inputs["goal_id"]
    existing = db.get_item(table, user_id, "goal_id", goal_id)
    if not existing:
        return f"Goal {goal_id} not found."

    fields = {}
    for k in ("title", "description", "target_date"):
        if inputs.get(k):
            fields[k] = inputs[k].strip() if isinstance(inputs[k], str) else inputs[k]
    if not fields:
        return "No fields supplied to update."
    fields["updated_at"] = _now()

    set_parts, names, values = [], {}, {}
    for i, (k, v) in enumerate(fields.items()):
        names[f"#k{i}"]  = k
        values[f":v{i}"] = v
        set_parts.append(f"#k{i} = :v{i}")
    table.update_item(
        Key={"user_id": user_id, "goal_id": goal_id},
        UpdateExpression="SET " + ", ".join(set_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )
    changed = ", ".join(f"{k}" for k in fields if k != "updated_at")
    return f"Updated goal '{fields.get('title', existing.get('title', goal_id))}': {changed}"


# ── Nutrition delete ──────────────────────────────────────────────────────────

def _delete_meal(user_id: str, inputs: dict) -> str:
    table = db.get_table(HEALTH_TABLE)
    log_date = inputs.get("date") or inputs.get("_today") or date.today().isoformat()
    item = table.get_item(Key={"user_id": user_id, "log_date": log_date}).get("Item")
    if not item or not item.get("foods"):
        return f"No foods on {log_date}."
    foods = list(item["foods"])
    target_id   = inputs.get("meal_id") or inputs.get("food_id")
    target_name = (inputs.get("name") or "").strip().lower()
    removed = None
    for i, m in enumerate(foods):
        if target_id and m.get("id") == target_id:
            removed = foods.pop(i)
            break
        if target_name and (m.get("name") or "").strip().lower() == target_name:
            removed = foods.pop(i)
            break
    if removed is None:
        return "No matching food found."
    item["foods"]      = foods
    item["updated_at"] = _now()
    table.put_item(Item=item)
    return f"Removed '{removed.get('name')}' from health log for {log_date}. {len(foods)} item(s) remaining."


def _clear_nutrition_log(user_id: str, inputs: dict) -> str:
    """Clear only the foods array on the day, keep exercises and totals."""
    table = db.get_table(HEALTH_TABLE)
    log_date = inputs.get("date") or inputs.get("_today") or date.today().isoformat()
    item = table.get_item(Key={"user_id": user_id, "log_date": log_date}).get("Item")
    if not item or not item.get("foods"):
        return f"No nutrition log for {log_date}."
    item["foods"]      = []
    item["updated_at"] = _now()
    table.put_item(Item=item)
    return f"Cleared nutrition portion of health log for {log_date}."


# ── Exercise extras ───────────────────────────────────────────────────────────

def _delete_exercise(user_id: str, inputs: dict) -> str:
    table = db.get_table(HEALTH_TABLE)
    log_date = inputs.get("date") or inputs.get("_today") or date.today().isoformat()
    item = table.get_item(Key={"user_id": user_id, "log_date": log_date}).get("Item")
    if not item or not item.get("exercises"):
        return f"No exercises on {log_date}."
    exs = list(item["exercises"])
    target_id   = inputs.get("exercise_id")
    target_name = (inputs.get("name") or "").strip().lower()
    removed = None
    for i, ex in enumerate(exs):
        if target_id and ex.get("id") == target_id:
            removed = exs.pop(i)
            break
        if target_name and (ex.get("name") or "").strip().lower() == target_name:
            removed = exs.pop(i)
            break
    if removed is None:
        return "No matching exercise found."
    item["exercises"]  = exs
    item["updated_at"] = _now()
    table.put_item(Item=item)
    return f"Removed '{removed.get('name')}' from exercise log for {log_date}."


def _list_exercise_days(user_id: str, inputs: dict) -> str:
    table = db.get_table(HEALTH_TABLE)
    items = db.query_by_user(table, user_id)
    items = [i for i in items if i.get("exercises")]
    items.sort(key=lambda x: x.get("log_date", ""), reverse=True)
    limit = int(inputs.get("limit", 7) or 7)
    items = items[:limit]
    if not items:
        return "No exercise logs yet."
    lines = ["Exercise days:"]
    for i in items:
        count = len(i.get("exercises", []))
        lines.append(f"- {i['log_date']}: {count} exercise(s)")
    return "\n".join(lines)


# ── Health ────────────────────────────────────────────────────────────────────

def _log_health(user_id: str, inputs: dict) -> str:
    table = db.get_table(HEALTH_TABLE)
    log_date = inputs.get("date") or inputs.get("_today") or date.today().isoformat()
    existing = table.get_item(Key={"user_id": user_id, "log_date": log_date}).get("Item") or {}
    item = {
        **existing,
        "user_id":    user_id,
        "log_date":   log_date,
        "foods":      existing.get("foods", []),
        "exercises":  existing.get("exercises", []),
        "notes":      existing.get("notes", ""),
        "created_at": existing.get("created_at") or _now(),
        "updated_at": _now(),
    }
    for k in ("weight", "sleep_hours"):
        if inputs.get(k) is not None:
            item[k] = Decimal(str(inputs[k]))
    for k in ("mood", "notes"):
        if inputs.get(k) is not None and inputs.get(k) != "":
            item[k] = inputs[k]
    # Preserve existing keys the caller didn't override
    for k in ("weight", "sleep_hours", "mood"):
        if k not in item and existing.get(k) is not None:
            item[k] = existing[k]
    table.put_item(Item=item)
    parts = [f"{k}={item[k]}" for k in ("weight", "sleep_hours", "mood") if k in item]
    return f"Logged health for {log_date}: {', '.join(parts) if parts else 'no new fields'}."


def _get_health_log(user_id: str, inputs: dict) -> str:
    table = db.get_table(HEALTH_TABLE)
    log_date = inputs.get("date") or inputs.get("_today") or date.today().isoformat()
    item = table.get_item(Key={"user_id": user_id, "log_date": log_date}).get("Item")
    if not item:
        return f"No health log for {log_date}."
    bits = []
    for k in ("weight", "sleep_hours", "mood"):
        if item.get(k) is not None and item.get(k) != "":
            bits.append(f"{k}: {item[k]}")
    if item.get("notes"):
        bits.append(f"notes: {item['notes']}")
    return f"Health {log_date}: " + ("; ".join(bits) if bits else "(no entries)")


def _list_health_logs(user_id: str, inputs: dict) -> str:
    table = db.get_table(HEALTH_TABLE)
    items = db.query_by_user(table, user_id)
    def _has_health(i):
        return any(i.get(k) is not None for k in ("weight", "sleep_hours", "mood"))
    items = [i for i in items if _has_health(i)]
    items.sort(key=lambda x: x.get("log_date", ""), reverse=True)
    limit = int(inputs.get("limit", 10) or 10)
    items = items[:limit]
    if not items:
        return "No health logs yet."
    lines = ["Health logs:"]
    for i in items:
        parts = []
        for k in ("weight", "sleep_hours", "mood"):
            if i.get(k) is not None:
                parts.append(f"{k}={i[k]}")
        lines.append(f"- {i['log_date']}: {', '.join(parts)}")
    return "\n".join(lines)


def _delete_health_log(user_id: str, inputs: dict) -> str:
    table = db.get_table(HEALTH_TABLE)
    d = inputs["date"]
    item = table.get_item(Key={"user_id": user_id, "log_date": d}).get("Item")
    if not item:
        return f"No health log for {d}."
    # Only null out health-specific fields; keep meals/exercises if present
    if item.get("foods") or item.get("exercises"):
        for k in ("weight", "sleep_hours", "mood"):
            item.pop(k, None)
        item["updated_at"] = _now()
        table.put_item(Item=item)
        return f"Cleared health metrics for {d} (kept foods/exercises)."
    table.delete_item(Key={"user_id": user_id, "log_date": d})
    return f"Deleted health log for {d}."


# ── Finances helpers ──────────────────────────────────────────────────────────

def _finances_common_update(table_name: str, key_name: str, user_id: str, item_id: str, fields: dict) -> str:
    table = db.get_table(table_name)
    existing = db.get_item(table, user_id, key_name, item_id)
    if not existing:
        return f"{key_name}={item_id} not found."
    fields = {k: v for k, v in fields.items() if v is not None and v != ""}
    if not fields:
        return "No fields supplied to update."
    # Coerce numeric
    for k in ("amount", "balance", "apr", "min_payment", "due_day"):
        if k in fields and not isinstance(fields[k], Decimal):
            fields[k] = Decimal(str(fields[k]))
    fields["updated_at"] = _now()
    set_parts, names, values = [], {}, {}
    for i, (k, v) in enumerate(fields.items()):
        names[f"#k{i}"]  = k
        values[f":v{i}"] = v
        set_parts.append(f"#k{i} = :v{i}")
    table.update_item(
        Key={"user_id": user_id, key_name: item_id},
        UpdateExpression="SET " + ", ".join(set_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )
    return f"Updated {key_name}={item_id}."


# Debts ---------------------------------------------------------------------
def _list_debts(user_id: str, inputs: dict) -> str:
    table = db.get_table(DEBTS_TABLE)
    items = db.query_by_user(table, user_id)
    if not items:
        return "No debts."
    lines = ["Debts:"]
    for d in items:
        lines.append(
            f"- {d.get('name')}: balance {d.get('balance')} "
            f"APR {d.get('apr', '?')} min {d.get('min_payment', '?')} "
            f"[id:{d.get('debt_id')}]"
        )
    return "\n".join(lines)


def _create_debt(user_id: str, inputs: dict) -> str:
    table = db.get_table(DEBTS_TABLE)
    did   = str(uuid.uuid4())
    item = {
        "user_id":    user_id,
        "debt_id":    did,
        "name":       inputs["name"].strip(),
        "balance":    Decimal(str(inputs["balance"])),
        "created_at": _now(),
        "updated_at": _now(),
    }
    for k in ("apr", "min_payment"):
        if inputs.get(k) is not None:
            item[k] = Decimal(str(inputs[k]))
    table.put_item(Item=item)
    return f"Created debt '{item['name']}' balance {item['balance']} [id:{did}]"


def _update_debt(user_id: str, inputs: dict) -> str:
    return _finances_common_update(
        DEBTS_TABLE, "debt_id", user_id, inputs["debt_id"],
        {k: inputs.get(k) for k in ("name", "balance", "apr", "min_payment")},
    )


def _delete_debt(user_id: str, inputs: dict) -> str:
    table = db.get_table(DEBTS_TABLE)
    did = inputs["debt_id"]
    existing = db.get_item(table, user_id, "debt_id", did)
    if not existing:
        return f"Debt {did} not found."
    db.delete_item(table, user_id, "debt_id", did)
    return f"Deleted debt '{existing.get('name', did)}'."


# Income --------------------------------------------------------------------
def _list_income(user_id: str, inputs: dict) -> str:
    table = db.get_table(INCOME_TABLE)
    items = db.query_by_user(table, user_id)
    if not items:
        return "No income sources."
    lines = ["Income:"]
    for i in items:
        lines.append(f"- {i.get('name')}: {i.get('amount')} {i.get('frequency', 'monthly')} [id:{i.get('income_id')}]")
    return "\n".join(lines)


def _create_income(user_id: str, inputs: dict) -> str:
    table = db.get_table(INCOME_TABLE)
    iid = str(uuid.uuid4())
    item = {
        "user_id":    user_id,
        "income_id":  iid,
        "name":       inputs["name"].strip(),
        "amount":     Decimal(str(inputs["amount"])),
        "frequency":  inputs.get("frequency", "monthly"),
        "created_at": _now(),
        "updated_at": _now(),
    }
    table.put_item(Item=item)
    return f"Created income '{item['name']}' {item['amount']} {item['frequency']} [id:{iid}]"


def _update_income(user_id: str, inputs: dict) -> str:
    return _finances_common_update(
        INCOME_TABLE, "income_id", user_id, inputs["income_id"],
        {k: inputs.get(k) for k in ("name", "amount", "frequency")},
    )


def _delete_income(user_id: str, inputs: dict) -> str:
    table = db.get_table(INCOME_TABLE)
    iid = inputs["income_id"]
    existing = db.get_item(table, user_id, "income_id", iid)
    if not existing:
        return f"Income {iid} not found."
    db.delete_item(table, user_id, "income_id", iid)
    return f"Deleted income '{existing.get('name', iid)}'."


# Expenses ------------------------------------------------------------------
def _list_expenses(user_id: str, inputs: dict) -> str:
    table = db.get_table(EXPENSES_TABLE)
    items = db.query_by_user(table, user_id)
    if not items:
        return "No fixed expenses."
    lines = ["Fixed expenses:"]
    for e in items:
        dd = f" due day {e['due_day']}" if e.get("due_day") else ""
        lines.append(
            f"- {e.get('name')}: {e.get('amount')} {e.get('frequency', 'monthly')}{dd} "
            f"[id:{e.get('expense_id')}]"
        )
    return "\n".join(lines)


def _create_expense(user_id: str, inputs: dict) -> str:
    table = db.get_table(EXPENSES_TABLE)
    eid = str(uuid.uuid4())
    item = {
        "user_id":    user_id,
        "expense_id": eid,
        "name":       inputs["name"].strip(),
        "amount":     Decimal(str(inputs["amount"])),
        "frequency":  inputs.get("frequency", "monthly"),
        "created_at": _now(),
        "updated_at": _now(),
    }
    if inputs.get("due_day") is not None:
        item["due_day"] = Decimal(str(inputs["due_day"]))
    table.put_item(Item=item)
    return f"Created expense '{item['name']}' {item['amount']} {item['frequency']} [id:{eid}]"


def _update_expense(user_id: str, inputs: dict) -> str:
    return _finances_common_update(
        EXPENSES_TABLE, "expense_id", user_id, inputs["expense_id"],
        {k: inputs.get(k) for k in ("name", "amount", "frequency", "due_day")},
    )


def _delete_expense(user_id: str, inputs: dict) -> str:
    table = db.get_table(EXPENSES_TABLE)
    eid = inputs["expense_id"]
    existing = db.get_item(table, user_id, "expense_id", eid)
    if not existing:
        return f"Expense {eid} not found."
    db.delete_item(table, user_id, "expense_id", eid)
    return f"Deleted expense '{existing.get('name', eid)}'."


def _get_finances_summary(user_id: str, inputs: dict) -> str:
    def _monthly(amount, freq):
        if amount is None: return Decimal(0)
        amt = amount if isinstance(amount, Decimal) else Decimal(str(amount))
        f = (freq or "monthly").lower()
        if f == "weekly":   return amt * Decimal("52") / Decimal("12")
        if f == "biweekly": return amt * Decimal("26") / Decimal("12")
        if f == "yearly":   return amt / Decimal("12")
        return amt
    inc_sum = Decimal(0)
    for i in db.query_by_user(db.get_table(INCOME_TABLE), user_id):
        inc_sum += _monthly(i.get("amount"), i.get("frequency"))
    exp_sum = Decimal(0)
    for e in db.query_by_user(db.get_table(EXPENSES_TABLE), user_id):
        exp_sum += _monthly(e.get("amount"), e.get("frequency"))
    debt_total = Decimal(0)
    for d in db.query_by_user(db.get_table(DEBTS_TABLE), user_id):
        bal = d.get("balance") or 0
        debt_total += bal if isinstance(bal, Decimal) else Decimal(str(bal))
    net = inc_sum - exp_sum
    return (
        f"Monthly income: {inc_sum:.2f}\n"
        f"Monthly outflow: {exp_sum:.2f}\n"
        f"Net monthly cash flow: {net:.2f}\n"
        f"Total debt balance: {debt_total:.2f}"
    )


# ── Bookmarks ─────────────────────────────────────────────────────────────────

def _create_bookmark(user_id: str, inputs: dict) -> str:
    table = db.get_table(BOOKMARKS_TABLE)
    bid = str(uuid.uuid4())
    item = {
        "user_id":     user_id,
        "bookmark_id": bid,
        "url":         inputs["url"].strip(),
        "title":       inputs.get("title", "").strip(),
        "description": inputs.get("description", ""),
        "tags":        [t.strip() for t in (inputs.get("tags") or []) if t and t.strip()],
        "created_at":  _now(),
        "updated_at":  _now(),
    }
    table.put_item(Item={k: v for k, v in item.items() if v not in (None, "", [])})
    return f"Bookmarked '{item['title'] or item['url']}' [id:{bid}]"


def _list_bookmarks(user_id: str, inputs: dict) -> str:
    table = db.get_table(BOOKMARKS_TABLE)
    items = db.query_by_user(table, user_id)
    tag = (inputs.get("tag") or "").strip().lower()
    if tag:
        items = [b for b in items if any((t or "").lower() == tag for t in b.get("tags", []))]
    if not items:
        return "No bookmarks."
    lines = ["Bookmarks:"]
    for b in items[:50]:
        tags_str = f" [{', '.join(b.get('tags', []))}]" if b.get("tags") else ""
        lines.append(f"- {b.get('title') or b.get('url')}{tags_str} → {b.get('url')} [id:{b.get('bookmark_id')}]")
    return "\n".join(lines)


def _update_bookmark(user_id: str, inputs: dict) -> str:
    table = db.get_table(BOOKMARKS_TABLE)
    bid = inputs["bookmark_id"]
    existing = db.get_item(table, user_id, "bookmark_id", bid)
    if not existing:
        return f"Bookmark {bid} not found."
    fields = {}
    for k in ("title", "description"):
        if inputs.get(k) is not None:
            fields[k] = inputs[k]
    if inputs.get("tags") is not None:
        fields["tags"] = [t.strip() for t in inputs["tags"] if t and t.strip()]
    if not fields:
        return "No fields supplied to update."
    fields["updated_at"] = _now()
    set_parts, names, values = [], {}, {}
    for i, (k, v) in enumerate(fields.items()):
        names[f"#k{i}"]  = k
        values[f":v{i}"] = v
        set_parts.append(f"#k{i} = :v{i}")
    table.update_item(
        Key={"user_id": user_id, "bookmark_id": bid},
        UpdateExpression="SET " + ", ".join(set_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )
    return f"Updated bookmark {bid}."


def _delete_bookmark(user_id: str, inputs: dict) -> str:
    table = db.get_table(BOOKMARKS_TABLE)
    bid = inputs["bookmark_id"]
    existing = db.get_item(table, user_id, "bookmark_id", bid)
    if not existing:
        return f"Bookmark {bid} not found."
    db.delete_item(table, user_id, "bookmark_id", bid)
    return f"Deleted bookmark '{existing.get('title', existing.get('url', bid))}'."


# ── Favorites ────────────────────────────────────────────────────────────────

def _add_favorite(user_id: str, inputs: dict) -> str:
    table = db.get_table(FAVORITES_TABLE)
    fid = str(uuid.uuid4())
    item = {
        "user_id":     user_id,
        "favorite_id": fid,
        "kind":        inputs["kind"].strip().lower(),
        "item_id":     inputs["item_id"].strip(),
        "label":       inputs.get("label", "").strip(),
        "tags":        [t.strip() for t in (inputs.get("tags") or []) if t and t.strip()],
        "created_at":  _now(),
    }
    table.put_item(Item={k: v for k, v in item.items() if v not in (None, "", [])})
    return f"Favorited {item['kind']} '{item.get('label') or item['item_id']}' [id:{fid}]"


def _list_favorites(user_id: str, inputs: dict) -> str:
    table = db.get_table(FAVORITES_TABLE)
    items = db.query_by_user(table, user_id)
    kind = (inputs.get("kind") or "").strip().lower()
    if kind:
        items = [f for f in items if (f.get("kind") or "").lower() == kind]
    if not items:
        return "No favorites."
    lines = ["Favorites:"]
    for f in items[:50]:
        lines.append(f"- [{f.get('kind', '?')}] {f.get('label') or f.get('item_id')} [id:{f.get('favorite_id')}]")
    return "\n".join(lines)


def _remove_favorite(user_id: str, inputs: dict) -> str:
    table = db.get_table(FAVORITES_TABLE)
    fid = inputs["favorite_id"]
    existing = db.get_item(table, user_id, "favorite_id", fid)
    if not existing:
        return f"Favorite {fid} not found."
    db.delete_item(table, user_id, "favorite_id", fid)
    return f"Removed favorite '{existing.get('label', fid)}'."


# ── Feeds ─────────────────────────────────────────────────────────────────────

def _list_feeds(user_id: str, inputs: dict) -> str:
    table = db.get_table(FEEDS_TABLE)
    items = db.query_by_user(table, user_id)
    if not items:
        return "No feed subscriptions."
    lines = ["Feeds:"]
    for f in items:
        lines.append(f"- {f.get('name') or f.get('url')} → {f.get('url')} [id:{f.get('feed_id')}]")
    return "\n".join(lines)


def _add_feed(user_id: str, inputs: dict) -> str:
    table = db.get_table(FEEDS_TABLE)
    fid = str(uuid.uuid4())
    item = {
        "user_id":    user_id,
        "feed_id":    fid,
        "url":        inputs["url"].strip(),
        "name":       (inputs.get("name") or "").strip(),
        "created_at": _now(),
    }
    table.put_item(Item={k: v for k, v in item.items() if v not in (None, "")})
    return f"Added feed '{item.get('name') or item['url']}' [id:{fid}]"


def _delete_feed(user_id: str, inputs: dict) -> str:
    table = db.get_table(FEEDS_TABLE)
    fid = inputs["feed_id"]
    existing = db.get_item(table, user_id, "feed_id", fid)
    if not existing:
        return f"Feed {fid} not found."
    db.delete_item(table, user_id, "feed_id", fid)
    return f"Deleted feed '{existing.get('name', existing.get('url', fid))}'."


# ── Links graph ──────────────────────────────────────────────────────────────

def _get_links(user_id: str, inputs: dict) -> str:
    import links_util

    entity_type = (inputs.get("entity_type") or "").strip().lower()
    entity_id   = (inputs.get("entity_id")   or "").strip()
    direction   = (inputs.get("direction")   or "both").strip().lower()

    if not entity_type or not entity_id:
        return "entity_type and entity_id are required."
    if entity_type not in links_util.LINK_TYPES:
        return f"Unsupported entity_type: {entity_type}"
    if direction not in ("outbound", "inbound", "both"):
        return "direction must be one of: outbound, inbound, both"

    outbound: list[dict] = []
    inbound:  list[dict] = []
    if direction in ("outbound", "both"):
        outbound = links_util.query_outbound(user_id, entity_type, entity_id)
    if direction in ("inbound", "both"):
        inbound  = links_util.query_inbound(user_id, entity_type, entity_id)

    if not outbound and not inbound:
        return f"No links found for {entity_type}:{entity_id}."

    lines: list[str] = []
    if outbound:
        lines.append(f"Outbound ({len(outbound)}):")
        for edge in outbound:
            lines.append(f"- {edge['target_type']}:{edge['target_id']}")
    if inbound:
        lines.append(f"Inbound ({len(inbound)}):")
        for edge in inbound:
            lines.append(f"- {edge['source_type']}:{edge['source_id']}")
    return "\n".join(lines)
