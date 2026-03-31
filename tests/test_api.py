#!/usr/bin/env python3
"""
End-to-end integration tests for the Memoire API.

Covers tasks, habits, journal, notes, settings, and tokens — all CRUD operations,
validation rules, and error cases.

Authentication uses a Personal Access Token (PAT). Token management endpoints
(/tokens) require a Cognito JWT and cannot be tested via PAT.

Required environment variables:
    TEST_PAT  - Personal Access Token (pat_...)

Optional:
    API_URL   - Base API URL (defaults to https://memoire-dev.edenforge.io)

Usage:
    TEST_PAT=pat_... python tests/test_api.py
    TEST_PAT=pat_... python tests/test_api.py --suite tasks
    python tests/test_api.py --pat pat_... --api-url https://...
"""

import argparse
import os
import sys
import traceback

import requests


# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_API_URL = "https://api.memoire-dev.edenforge.io"
API_URL         = os.environ.get("API_URL", DEFAULT_API_URL).rstrip("/")
TEST_PAT        = os.environ.get("TEST_PAT", "")

# ── Output helpers ────────────────────────────────────────────────────────────

PASS  = "\033[92mPASS\033[0m"
FAIL  = "\033[91mFAIL\033[0m"
SKIP  = "\033[93mSKIP\033[0m"
BOLD  = "\033[1m"
RESET = "\033[0m"

results = {"passed": 0, "failed": 0, "errors": []}


def check(label: str, condition: bool, detail: str = "") -> bool:
    if condition:
        print(f"  [{PASS}] {label}")
        results["passed"] += 1
    else:
        print(f"  [{FAIL}] {label}")
        if detail:
            print(f"         {detail}")
        results["failed"] += 1
        results["errors"].append(label)
    return condition


def section(title: str) -> None:
    print(f"\n{BOLD}{title}{RESET}")
    print("-" * (len(title) + 2))


# ── Request helpers ───────────────────────────────────────────────────────────

def api(method: str, path: str, token: str, body: dict = None, params: dict = None) -> requests.Response:
    url     = f"{API_URL}{path}"
    headers = {"Authorization": token, "Content-Type": "application/json"}
    kwargs  = {"headers": headers, "timeout": 10}
    if body   is not None: kwargs["json"]   = body
    if params is not None: kwargs["params"] = params
    return requests.request(method, url, **kwargs)


# ── Tasks ─────────────────────────────────────────────────────────────────────

def test_tasks(token: str) -> None:
    section("Tasks — auth enforcement")
    r = requests.get(f"{API_URL}/tasks", timeout=10)
    check("No token returns 401", r.status_code == 401, f"Got {r.status_code}")
    r2 = requests.get(f"{API_URL}/tasks", headers={"Authorization": "Bearer bad.token"}, timeout=10)
    check("Invalid token returns 401", r2.status_code == 401, f"Got {r2.status_code}")

    section("Tasks — create")
    r = api("POST", "/tasks", token, {
        "title": "Integration test task",
        "description": "Created by test_api.py",
        "status": "todo",
        "priority": "high",
        "due_date": "2099-12-31",
    })
    check("Valid create returns 201", r.status_code == 201, f"Got {r.status_code}: {r.text}")
    task = r.json()
    task_id = task.get("task_id")
    check("Has task_id",    bool(task_id))
    check("Title matches",  task.get("title")    == "Integration test task")
    check("Status is todo", task.get("status")   == "todo")
    check("Priority high",  task.get("priority") == "high")
    check("Has created_at", "created_at" in task)
    check("Has updated_at", "updated_at" in task)

    check("Missing title → 400",
          api("POST", "/tasks", token, {"description": "No title"}).status_code == 400)
    check("Invalid status → 400",
          api("POST", "/tasks", token, {"title": "T", "status": "invalid"}).status_code == 400)
    check("Invalid priority → 400",
          api("POST", "/tasks", token, {"title": "T", "priority": "critical"}).status_code == 400)

    r5 = api("POST", "/tasks", token, {"title": "Minimal"})
    check("Title-only create returns 201",    r5.status_code == 201, f"Got {r5.status_code}")
    check("Defaults status to todo",          r5.json().get("status")   == "todo")
    check("Defaults priority to medium",      r5.json().get("priority") == "medium")
    if r5.json().get("task_id"):
        api("DELETE", f"/tasks/{r5.json()['task_id']}", token)

    if not task_id:
        print(f"  [{SKIP}] Skipping remaining task tests — creation failed")
        return

    section("Tasks — get")
    r = api("GET", f"/tasks/{task_id}", token)
    check("Get returns 200",      r.status_code == 200)
    check("task_id matches",      r.json().get("task_id") == task_id)
    check("Non-existent → 404",   api("GET", "/tasks/no-such-id", token).status_code == 404)

    section("Tasks — list")
    r = api("GET", "/tasks", token)
    check("List returns 200",         r.status_code == 200)
    ids = [t["task_id"] for t in r.json()]
    check("Created task in list",     task_id in ids, f"IDs: {ids}")

    section("Tasks — update")
    r = api("PUT", f"/tasks/{task_id}", token, {"status": "in_progress", "priority": "low"})
    check("Partial update returns 200", r.status_code == 200)
    t = r.json()
    check("Status updated",    t.get("status")   == "in_progress")
    check("Priority updated",  t.get("priority") == "low")
    check("Title unchanged",   t.get("title")    == "Integration test task")
    check("updated_at changed", t.get("updated_at") != t.get("created_at"))

    check("Invalid status update → 400",
          api("PUT", f"/tasks/{task_id}", token, {"status": "not_valid"}).status_code == 400)
    check("Empty body → 400",
          api("PUT", f"/tasks/{task_id}", token, {}).status_code == 400)
    check("Update non-existent → 404",
          api("PUT", "/tasks/no-such-id", token, {"title": "Ghost"}).status_code == 404)

    section("Tasks — delete")
    check("Delete returns 204",
          api("DELETE", f"/tasks/{task_id}", token).status_code == 204)
    check("Deleted task returns 404",
          api("GET", f"/tasks/{task_id}", token).status_code == 404)
    check("Double delete returns 404",
          api("DELETE", f"/tasks/{task_id}", token).status_code == 404)


# ── Habits ────────────────────────────────────────────────────────────────────

def test_habits(token: str) -> None:
    section("Habits — create")
    r = api("POST", "/habits", token, {"name": "Integration test habit", "notify_time": "08:00"})
    check("Valid create returns 201", r.status_code == 201, f"Got {r.status_code}: {r.text}")
    habit = r.json()
    habit_id = habit.get("habit_id")
    check("Has habit_id",          bool(habit_id))
    check("Name matches",          habit.get("name")        == "Integration test habit")
    check("notify_time set",       habit.get("notify_time") == "08:00")
    check("Has created_at",        "created_at" in habit)
    check("history is list",       isinstance(habit.get("history"), list))
    check("current_streak is int", isinstance(habit.get("current_streak"), int))
    check("best_streak is int",    isinstance(habit.get("best_streak"), int))

    check("Missing name → 400",
          api("POST", "/habits", token, {}).status_code == 400)
    check("Invalid notify_time format → 400",
          api("POST", "/habits", token, {"name": "T", "notify_time": "8am"}).status_code == 400)
    check("Invalid notify_time value → 400",
          api("POST", "/habits", token, {"name": "T", "notify_time": "25:99"}).status_code == 400)

    r2 = api("POST", "/habits", token, {"name": "Name-only habit"})
    check("Name-only create returns 201", r2.status_code == 201, f"Got {r2.status_code}")
    if r2.json().get("habit_id"):
        api("DELETE", f"/habits/{r2.json()['habit_id']}", token)

    if not habit_id:
        print(f"  [{SKIP}] Skipping remaining habit tests — creation failed")
        return

    section("Habits — list")
    r = api("GET", "/habits", token)
    check("List returns 200",        r.status_code == 200)
    ids = [h["habit_id"] for h in r.json()]
    check("Created habit in list",   habit_id in ids, f"IDs: {ids}")
    listed = next((h for h in r.json() if h["habit_id"] == habit_id), None)
    check("List item has history",   listed is not None and isinstance(listed.get("history"), list))
    check("List item has done_today", listed is not None and "done_today" in listed)

    section("Habits — update")
    r = api("PUT", f"/habits/{habit_id}", token, {"name": "Updated habit name", "notify_time": "09:30"})
    check("Update returns 200",  r.status_code == 200)
    check("Name updated",        r.json().get("name")        == "Updated habit name")
    check("notify_time updated", r.json().get("notify_time") == "09:30")

    check("Invalid notify_time on update → 400",
          api("PUT", f"/habits/{habit_id}", token, {"notify_time": "bad"}).status_code == 400)
    check("Update non-existent → 404",
          api("PUT", "/habits/no-such-id", token, {"name": "Ghost"}).status_code == 404)

    section("Habits — toggle")
    r = api("POST", f"/habits/{habit_id}/toggle", token, {})
    check("Toggle (no date) returns 200",  r.status_code == 200, f"Got {r.status_code}: {r.text}")
    d = r.json()
    check("Response has logged field",     "logged" in d)
    check("Response has date field",       "date"   in d)
    first_logged = d.get("logged")

    r2 = api("POST", f"/habits/{habit_id}/toggle", token, {})
    check("Second toggle returns 200",     r2.status_code == 200)
    check("Second toggle reverses state",  r2.json().get("logged") == (not first_logged))

    check("Future date → 400",
          api("POST", f"/habits/{habit_id}/toggle", token, {"date": "2099-01-01"}).status_code == 400)
    check("Bad date format → 400",
          api("POST", f"/habits/{habit_id}/toggle", token, {"date": "not-a-date"}).status_code == 400)
    check("Toggle non-existent habit → 404",
          api("POST", "/habits/no-such-id/toggle", token, {}).status_code == 404)

    section("Habits — delete")
    check("Delete returns 204",
          api("DELETE", f"/habits/{habit_id}", token).status_code == 204)
    r = api("GET", "/habits", token)
    ids_after = [h["habit_id"] for h in r.json()]
    check("Deleted habit gone from list", habit_id not in ids_after)
    check("Delete non-existent → 404",
          api("DELETE", f"/habits/{habit_id}", token).status_code == 404)


# ── Journal ───────────────────────────────────────────────────────────────────

TEST_JOURNAL_DATE = "2099-06-15"


def test_journal(token: str) -> None:
    # Clean up from any previous run
    api("DELETE", f"/journal/{TEST_JOURNAL_DATE}", token)

    section("Journal — upsert (create)")
    r = api("PUT", f"/journal/{TEST_JOURNAL_DATE}", token, {
        "title": "Integration test entry",
        "body":  "Test body content",
        "mood":  "good",
        "tags":  ["testing", "integration"],
    })
    check("Create returns 200", r.status_code == 200, f"Got {r.status_code}: {r.text}")
    entry = r.json()
    check("entry_date matches",   entry.get("entry_date") == TEST_JOURNAL_DATE)
    check("Title matches",        entry.get("title")      == "Integration test entry")
    check("Body matches",         entry.get("body")       == "Test body content")
    check("Mood matches",         entry.get("mood")       == "good")
    check("Tags is list",         isinstance(entry.get("tags"), list))
    check("Tags content correct", set(entry.get("tags", [])) == {"testing", "integration"})
    check("Has created_at",       "created_at" in entry)
    check("Has updated_at",       "updated_at" in entry)

    check("Invalid mood → 400",
          api("PUT", f"/journal/{TEST_JOURNAL_DATE}", token, {"mood": "fantastic"}).status_code == 400)
    check("Invalid date format → 400",
          api("PUT", "/journal/not-a-date", token, {"title": "Bad"}).status_code == 400)

    section("Journal — get")
    r = api("GET", f"/journal/{TEST_JOURNAL_DATE}", token)
    check("Get returns 200",     r.status_code == 200)
    check("Full body returned",  r.json().get("body") == "Test body content")
    check("Non-existent → 404",  api("GET", "/journal/2099-01-01", token).status_code == 404)

    section("Journal — list")
    r = api("GET", "/journal", token)
    check("List returns 200",          r.status_code == 200)
    check("Returns list",              isinstance(r.json(), list))
    dates = [e["entry_date"] for e in r.json()]
    check("Test entry in list",        TEST_JOURNAL_DATE in dates, f"Dates: {dates}")
    listed = next((e for e in r.json() if e["entry_date"] == TEST_JOURNAL_DATE), None)
    check("List item has preview",     listed is not None and "preview" in listed)

    section("Journal — search")
    r = api("GET", "/journal", token, params={"q": "Integration test"})
    check("Search returns 200",         r.status_code == 200)
    check("Search finds test entry",    any(e["entry_date"] == TEST_JOURNAL_DATE for e in r.json()),
          f"Got: {r.json()}")
    r2 = api("GET", "/journal", token, params={"q": "xyzzy_no_match_12345"})
    check("Search no-match returns []", r2.json() == [], f"Got {r2.json()}")

    section("Journal — upsert (update)")
    r = api("PUT", f"/journal/{TEST_JOURNAL_DATE}", token, {
        "title": "Updated title",
        "mood":  "great",
        "tags":  "updated, integration",
    })
    check("Update returns 200",         r.status_code == 200)
    check("Title updated",              r.json().get("title") == "Updated title")
    check("Mood updated",               r.json().get("mood")  == "great")
    check("Tags accept comma-string",   "updated" in r.json().get("tags", []))
    check("created_at preserved",       r.json().get("created_at") == entry.get("created_at"))

    section("Journal — delete")
    check("Delete returns 204",
          api("DELETE", f"/journal/{TEST_JOURNAL_DATE}", token).status_code == 204)
    check("Deleted entry returns 404",
          api("GET", f"/journal/{TEST_JOURNAL_DATE}", token).status_code == 404)
    check("Delete non-existent → 404",
          api("DELETE", f"/journal/{TEST_JOURNAL_DATE}", token).status_code == 404)


# ── Notes ─────────────────────────────────────────────────────────────────────

def test_notes(token: str) -> None:
    section("Notes — folders: list (auto-creates Inbox)")
    r = api("GET", "/notes/folders", token)
    check("List returns 200",         r.status_code == 200, f"Got {r.status_code}: {r.text}")
    folders = r.json()
    check("Returns list",             isinstance(folders, list))
    check("Inbox folder exists",      any(f["name"] == "Inbox" for f in folders),
          f"Folders: {[f['name'] for f in folders]}")

    section("Notes — folders: create")
    r = api("POST", "/notes/folders", token, {"name": "Test folder"})
    check("Create folder returns 201", r.status_code == 201, f"Got {r.status_code}: {r.text}")
    folder = r.json()
    folder_id = folder.get("folder_id")
    check("Has folder_id",   bool(folder_id))
    check("Name matches",    folder.get("name") == "Test folder")
    check("parent_id null",  folder.get("parent_id") is None)
    check("Has created_at",  "created_at" in folder)

    check("Missing name → 400",
          api("POST", "/notes/folders", token, {}).status_code == 400)
    check("Non-existent parent → 404",
          api("POST", "/notes/folders", token, {"name": "T", "parent_id": "no-such-id"}).status_code == 404)

    # Create a subfolder to verify parent_id support
    r2 = api("POST", "/notes/folders", token, {"name": "Sub folder", "parent_id": folder_id})
    check("Subfolder create returns 201", r2.status_code == 201, f"Got {r2.status_code}")
    check("parent_id set",                r2.json().get("parent_id") == folder_id)
    sub_folder_id = r2.json().get("folder_id")

    section("Notes — folders: rename")
    r = api("PUT", f"/notes/folders/{folder_id}", token, {"name": "Renamed folder"})
    check("Rename returns 200",  r.status_code == 200)
    check("Name updated",        r.json().get("name") == "Renamed folder")
    check("Missing name → 400",
          api("PUT", f"/notes/folders/{folder_id}", token, {}).status_code == 400)
    check("Rename non-existent → 404",
          api("PUT", "/notes/folders/no-such-id", token, {"name": "X"}).status_code == 404)

    if not folder_id:
        print(f"  [{SKIP}] Skipping note tests — folder creation failed")
        return

    section("Notes — create")
    r = api("POST", "/notes", token, {
        "folder_id": folder_id,
        "title":     "Integration test note",
        "body":      "# Test\n\nNote body content.",
        "tags":      ["test", "integration"],
    })
    check("Create returns 201", r.status_code == 201, f"Got {r.status_code}: {r.text}")
    note = r.json()
    note_id = note.get("note_id")
    check("Has note_id",         bool(note_id))
    check("Title matches",       note.get("title")     == "Integration test note")
    check("Body matches",        note.get("body")       == "# Test\n\nNote body content.")
    check("folder_id matches",   note.get("folder_id") == folder_id)
    check("Tags is list",        isinstance(note.get("tags"), list))
    check("Has created_at",      "created_at" in note)
    check("Has updated_at",      "updated_at" in note)

    check("Missing folder_id → 400",
          api("POST", "/notes", token, {"title": "No folder"}).status_code == 400)
    check("Non-existent folder_id → 404",
          api("POST", "/notes", token, {"folder_id": "no-such-id", "title": "T"}).status_code == 404)

    if not note_id:
        print(f"  [{SKIP}] Skipping note get/update/delete — creation failed")
        api("DELETE", f"/notes/folders/{sub_folder_id}", token)
        api("DELETE", f"/notes/folders/{folder_id}", token)
        return

    section("Notes — get")
    r = api("GET", f"/notes/{note_id}", token)
    check("Get returns 200",      r.status_code == 200)
    check("Full body returned",   r.json().get("body") == "# Test\n\nNote body content.")
    check("Non-existent → 404",   api("GET", "/notes/no-such-id", token).status_code == 404)

    section("Notes — list")
    r = api("GET", "/notes", token)
    check("List returns 200",      r.status_code == 200)
    check("Returns list",          isinstance(r.json(), list))
    ids = [n["note_id"] for n in r.json()]
    check("Created note in list",  note_id in ids, f"IDs: {ids}")
    listed = next((n for n in r.json() if n["note_id"] == note_id), None)
    check("List item has preview", listed is not None and "preview" in listed)

    section("Notes — search")
    r = api("GET", "/notes", token, params={"q": "Integration test note"})
    check("Search returns 200",       r.status_code == 200)
    check("Search finds test note",   any(n["note_id"] == note_id for n in r.json()),
          f"Got: {r.json()}")
    r2 = api("GET", "/notes", token, params={"q": "xyzzy_no_match_12345"})
    check("Search no-match returns []", r2.json() == [], f"Got {r2.json()}")

    section("Notes — update")
    r = api("PUT", f"/notes/{note_id}", token, {
        "title": "Updated note title",
        "body":  "Updated body",
        "tags":  "updated, test",
    })
    check("Update returns 200",         r.status_code == 200)
    check("Title updated",              r.json().get("title") == "Updated note title")
    check("Body updated",               r.json().get("body")  == "Updated body")
    check("Tags accept comma-string",   "updated" in r.json().get("tags", []))
    check("updated_at refreshed",       r.json().get("updated_at") != note.get("updated_at"))

    check("Update non-existent → 404",
          api("PUT", "/notes/no-such-id", token, {"title": "X"}).status_code == 404)
    check("Move to non-existent folder → 404",
          api("PUT", f"/notes/{note_id}", token, {"folder_id": "no-such-id"}).status_code == 404)

    section("Notes — delete")
    check("Delete note returns 204",
          api("DELETE", f"/notes/{note_id}", token).status_code == 204)
    check("Deleted note returns 404",
          api("GET", f"/notes/{note_id}", token).status_code == 404)
    check("Delete non-existent → 404",
          api("DELETE", f"/notes/no-such-id", token).status_code == 404)

    section("Notes — folder delete (recursive)")
    # Create a note in sub_folder to verify recursive delete
    rn = api("POST", "/notes", token, {"folder_id": sub_folder_id, "title": "Nested note"})
    nested_note_id = rn.json().get("note_id") if rn.status_code == 201 else None

    check("Delete folder returns 204",
          api("DELETE", f"/notes/folders/{folder_id}", token).status_code == 204)
    check("Deleted folder gone from list",
          folder_id not in [f["folder_id"] for f in api("GET", "/notes/folders", token).json()])
    if nested_note_id:
        check("Nested note also deleted",
              api("GET", f"/notes/{nested_note_id}", token).status_code == 404)


# ── Settings ──────────────────────────────────────────────────────────────────

def test_settings(token: str) -> None:
    section("Settings — get")
    r = api("GET", "/settings", token)
    check("Get returns 200",              r.status_code == 200, f"Got {r.status_code}: {r.text}")
    s = r.json()
    check("Has dark_mode key",            "dark_mode" in s)
    check("Has ntfy_url key",             "ntfy_url" in s)
    check("Has autosave_seconds key",     "autosave_seconds" in s)
    check("dark_mode is bool",            isinstance(s.get("dark_mode"), bool))
    check("autosave_seconds is int",      isinstance(s.get("autosave_seconds"), int))

    # Capture originals to restore later
    original = {k: s[k] for k in ("dark_mode", "ntfy_url", "autosave_seconds")}

    section("Settings — update")
    r = api("PUT", "/settings", token, {"dark_mode": True})
    check("Update dark_mode returns 200", r.status_code == 200)
    check("dark_mode updated to True",    r.json().get("dark_mode") is True)

    r = api("PUT", "/settings", token, {"ntfy_url": "https://ntfy.example.com/test"})
    check("Update ntfy_url returns 200",  r.status_code == 200)
    check("ntfy_url updated",             r.json().get("ntfy_url") == "https://ntfy.example.com/test")

    r = api("PUT", "/settings", token, {"autosave_seconds": 60})
    check("Update autosave_seconds returns 200", r.status_code == 200)
    check("autosave_seconds updated",            r.json().get("autosave_seconds") == 60)

    r = api("PUT", "/settings", token, {"unknown_field": "ignored", "dark_mode": False})
    check("Unknown fields ignored",       r.status_code == 200)
    check("Known field still updated",    r.json().get("dark_mode") is False)
    check("Unknown field not in response", "unknown_field" not in r.json())

    # Verify persistence
    r = api("GET", "/settings", token)
    check("Changes persisted on GET",     r.json().get("autosave_seconds") == 60)

    section("Settings — test notification (no URL configured)")
    api("PUT", "/settings", token, {"ntfy_url": ""})
    r = api("POST", "/settings/test-notification", token, {})
    check("No ntfy URL returns error",    r.status_code in (400, 500), f"Got {r.status_code}: {r.text}")

    # Restore original settings
    api("PUT", "/settings", token, original)


# ── Tokens ────────────────────────────────────────────────────────────────────

def test_tokens(token: str) -> None:
    """Verify PAT auth enforcement on the /tokens management endpoints.

    Full token lifecycle (create/list/revoke) requires a Cognito JWT and
    cannot be tested with a PAT. These checks confirm the boundary is enforced.
    """
    section("Tokens — unauthenticated access blocked")
    r = requests.get(f"{API_URL}/tokens", timeout=10)
    check("No token returns 401", r.status_code == 401, f"Got {r.status_code}")

    section("Tokens — PAT cannot manage tokens")
    r = api("GET", "/tokens", token)
    check("PAT blocked from listing tokens (401)", r.status_code == 401, f"Got {r.status_code}: {r.text}")

    r = api("POST", "/tokens", token, {"name": "should-fail"})
    check("PAT blocked from creating token (401)", r.status_code == 401, f"Got {r.status_code}: {r.text}")

    r = api("DELETE", "/tokens/any-id", token)
    check("PAT blocked from revoking token (401)", r.status_code == 401, f"Got {r.status_code}: {r.text}")


# ── Suites + entry point ──────────────────────────────────────────────────────

SUITES = {
    "tasks":    test_tasks,
    "habits":   test_habits,
    "journal":  test_journal,
    "notes":    test_notes,
    "settings": test_settings,
    "tokens":   test_tokens,
}


def validate_config(pat: str) -> None:
    if not API_URL:
        print("API_URL is not set.")
        sys.exit(1)
    if not pat:
        print("No PAT provided. Set TEST_PAT or pass --pat <token>.")
        sys.exit(1)
    if not pat.startswith("pat_"):
        print(f"Warning: token doesn't start with 'pat_' — is this a valid PAT?")


def main() -> None:
    global API_URL
    parser = argparse.ArgumentParser(description="Memoire API end-to-end tests")
    parser.add_argument("--pat", default=TEST_PAT,
                        help="Personal Access Token (or set TEST_PAT env var)")
    parser.add_argument("--api-url", default=API_URL,
                        help=f"Base API URL (default: {DEFAULT_API_URL})")
    parser.add_argument("--suite", choices=list(SUITES), default=None,
                        help="Run only this suite (default: all)")
    args = parser.parse_args()

    API_URL = args.api_url.rstrip("/")

    validate_config(args.pat)

    suites_to_run = {args.suite: SUITES[args.suite]} if args.suite else SUITES

    print(f"\n{BOLD}Memoire API — End-to-End Tests{RESET}")
    print(f"API URL: {API_URL}")
    print(f"Suites:  {', '.join(suites_to_run)}")

    token = args.pat

    for name, suite_fn in suites_to_run.items():
        print(f"\n{BOLD}{'=' * 40}{RESET}")
        print(f"{BOLD}Suite: {name.upper()}{RESET}")
        try:
            suite_fn(token)
        except Exception:
            print(f"\n  [{FAIL}] Unexpected error in {name} suite:")
            traceback.print_exc()
            results["failed"] += 1

    total = results["passed"] + results["failed"]
    print(f"\n{'=' * 40}")
    print(f"{BOLD}Results: {results['passed']}/{total} passed{RESET}")
    if results["errors"]:
        print("\nFailed checks:")
        for err in results["errors"]:
            print(f"  - {err}")
    print()

    sys.exit(0 if results["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
