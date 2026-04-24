"""MCP server for the Memoire personal productivity API."""

import base64
import json
import os

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Memoire",
    instructions=(
        "Personal productivity API for tasks, notes, habits, journal, health, "
        "nutrition, goals, bookmarks, favorites, feeds, finances, diagrams, "
        "and an AI assistant. Authenticate with a Personal Access Token (PAT)."
    ),
)

_BASE_URL = os.environ.get("MEMOIRE_API_URL", "").rstrip("/")
_PAT = os.environ.get("MEMOIRE_PAT", "")


def _headers() -> dict[str, str]:
    return {"Authorization": _PAT, "Content-Type": "application/json"}


async def _request(
    method: str,
    path: str,
    *,
    body: dict | None = None,
    params: dict | None = None,
) -> dict | list | str:
    if not _BASE_URL:
        return {"error": "MEMOIRE_API_URL is not configured"}
    if not _PAT:
        return {"error": "MEMOIRE_PAT is not configured"}

    url = f"{_BASE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method,
                url,
                headers=_headers(),
                json=body if body else None,
                params=params,
            )
    except httpx.RequestError as exc:
        return {"error": f"Request failed: {exc}"}

    if resp.status_code == 204:
        return {"ok": True}

    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type:
        return resp.json()
    if "application/zip" in content_type or "application/octet-stream" in content_type:
        return {"binary": True, "base64": base64.b64encode(resp.content).decode(), "content_type": content_type}
    return resp.text


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_tasks() -> str:
    """List all tasks."""
    return json.dumps(await _request("GET", "/tasks"))


@mcp.tool()
async def get_task(task_id: str) -> str:
    """Get a single task by ID."""
    return json.dumps(await _request("GET", f"/tasks/{task_id}"))


@mcp.tool()
async def create_task(
    title: str,
    description: str = "",
    status: str = "todo",
    priority: str = "medium",
    due_date: str | None = None,
    folder_id: str | None = None,
    notifications: dict | None = None,
) -> str:
    """Create a task.

    Args:
        title: Task title (required).
        description: Task description.
        status: todo, in_progress, or done.
        priority: low, medium, or high.
        due_date: Optional due date (YYYY-MM-DD).
        folder_id: Optional folder UUID.
        notifications: Optional reminder config. Shape: {"before_due": [...], "recurring": "1h"|"1d"|"1w"}.
            before_due values must be from: "1h", "1d", "3d".
    """
    body: dict = {"title": title, "description": description, "status": status, "priority": priority}
    if due_date:
        body["due_date"] = due_date
    if folder_id:
        body["folder_id"] = folder_id
    if notifications is not None:
        body["notifications"] = notifications
    return json.dumps(await _request("POST", "/tasks", body=body))


@mcp.tool()
async def update_task(
    task_id: str,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    due_date: str | None = None,
    folder_id: str | None = None,
    notifications: dict | None = None,
) -> str:
    """Update a task. Only provided fields are changed.

    Args:
        task_id: Task UUID.
        title: New title.
        description: New description.
        status: todo, in_progress, or done.
        priority: low, medium, or high.
        due_date: Due date (YYYY-MM-DD) or empty string to clear.
        folder_id: Folder UUID or empty string to clear.
        notifications: Reminder config {"before_due": [...], "recurring": "1h"|"1d"|"1w"}. Pass {} to clear.
            before_due values must be from: "1h", "1d", "3d".
    """
    body: dict = {}
    if title is not None:
        body["title"] = title
    if description is not None:
        body["description"] = description
    if status is not None:
        body["status"] = status
    if priority is not None:
        body["priority"] = priority
    if due_date is not None:
        body["due_date"] = due_date if due_date else None
    if folder_id is not None:
        body["folder_id"] = folder_id if folder_id else None
    if notifications is not None:
        body["notifications"] = notifications or None
    return json.dumps(await _request("PUT", f"/tasks/{task_id}", body=body))


@mcp.tool()
async def delete_task(task_id: str) -> str:
    """Delete a task.

    Args:
        task_id: Task UUID.
    """
    return json.dumps(await _request("DELETE", f"/tasks/{task_id}"))


@mcp.tool()
async def list_task_folders() -> str:
    """List all task folders."""
    return json.dumps(await _request("GET", "/tasks/folders"))


@mcp.tool()
async def create_task_folder(name: str, parent_id: str | None = None) -> str:
    """Create a task folder.

    Args:
        name: Folder name.
        parent_id: Optional parent folder UUID.
    """
    body: dict = {"name": name}
    if parent_id:
        body["parent_id"] = parent_id
    return json.dumps(await _request("POST", "/tasks/folders", body=body))


@mcp.tool()
async def update_task_folder(folder_id: str, name: str, parent_id: str | None = None) -> str:
    """Update a task folder.

    Args:
        folder_id: Folder UUID.
        name: New folder name.
        parent_id: New parent folder UUID or empty string to clear.
    """
    body: dict = {"name": name}
    if parent_id is not None:
        body["parent_id"] = parent_id if parent_id else None
    return json.dumps(await _request("PUT", f"/tasks/folders/{folder_id}", body=body))


@mcp.tool()
async def delete_task_folder(folder_id: str) -> str:
    """Delete a task folder.

    Args:
        folder_id: Folder UUID.
    """
    return json.dumps(await _request("DELETE", f"/tasks/folders/{folder_id}"))


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_notes(q: str | None = None) -> str:
    """List notes (summaries with truncated body). Supports full-text search.

    Args:
        q: Optional search query across title, body, and tags.
    """
    params = {"q": q} if q else None
    return json.dumps(await _request("GET", "/notes", params=params))


@mcp.tool()
async def get_note(note_id: str) -> str:
    """Get a single note with full body.

    Args:
        note_id: Note UUID.
    """
    return json.dumps(await _request("GET", f"/notes/{note_id}"))


@mcp.tool()
async def create_note(
    folder_id: str,
    title: str = "",
    body: str = "",
    tags: list[str] | None = None,
) -> str:
    """Create a note.

    Args:
        folder_id: Folder UUID (required).
        title: Note title.
        body: Markdown content.
        tags: Optional list of tags.
    """
    payload: dict = {"folder_id": folder_id, "title": title, "body": body}
    if tags:
        payload["tags"] = tags
    return json.dumps(await _request("POST", "/notes", body=payload))


@mcp.tool()
async def update_note(
    note_id: str,
    folder_id: str | None = None,
    title: str | None = None,
    body: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Update a note. Only provided fields are changed.

    Args:
        note_id: Note UUID.
        folder_id: Move to a different folder.
        title: New title.
        body: New markdown content.
        tags: New tags list.
    """
    payload: dict = {}
    if folder_id is not None:
        payload["folder_id"] = folder_id
    if title is not None:
        payload["title"] = title
    if body is not None:
        payload["body"] = body
    if tags is not None:
        payload["tags"] = tags
    return json.dumps(await _request("PUT", f"/notes/{note_id}", body=payload))


@mcp.tool()
async def delete_note(note_id: str) -> str:
    """Delete a note.

    Args:
        note_id: Note UUID.
    """
    return json.dumps(await _request("DELETE", f"/notes/{note_id}"))


@mcp.tool()
async def list_note_folders() -> str:
    """List all note folders."""
    return json.dumps(await _request("GET", "/notes/folders"))


@mcp.tool()
async def create_note_folder(name: str, parent_id: str | None = None) -> str:
    """Create a note folder.

    Args:
        name: Folder name.
        parent_id: Optional parent folder UUID.
    """
    payload: dict = {"name": name}
    if parent_id:
        payload["parent_id"] = parent_id
    return json.dumps(await _request("POST", "/notes/folders", body=payload))


@mcp.tool()
async def update_note_folder(folder_id: str, name: str, parent_id: str | None = None) -> str:
    """Update a note folder.

    Args:
        folder_id: Folder UUID.
        name: New folder name.
        parent_id: New parent folder UUID or empty string to clear.
    """
    payload: dict = {"name": name}
    if parent_id is not None:
        payload["parent_id"] = parent_id if parent_id else None
    return json.dumps(await _request("PUT", f"/notes/folders/{folder_id}", body=payload))


@mcp.tool()
async def delete_note_folder(folder_id: str) -> str:
    """Delete a note folder.

    Args:
        folder_id: Folder UUID.
    """
    return json.dumps(await _request("DELETE", f"/notes/folders/{folder_id}"))


@mcp.tool()
async def request_note_image_upload(filename: str, content_type: str) -> str:
    """Request a presigned S3 URL to upload an inline note image.

    Upload the image directly to the returned URL via PUT. Reference the
    returned key in Markdown as the ?key= query parameter on GET /notes/images.

    Args:
        filename: Image filename (e.g. screenshot.png).
        content_type: MIME type (e.g. image/png, image/jpeg).
    """
    return json.dumps(await _request(
        "POST", "/notes/images", body={"filename": filename, "content_type": content_type}
    ))


@mcp.tool()
async def get_note_image(key: str) -> str:
    """Get a redirect URL for an inline note image.

    Args:
        key: S3 object key returned by request_note_image_upload.
    """
    return json.dumps(await _request("GET", "/notes/images", params={"key": key}))


@mcp.tool()
async def request_note_attachment_upload(
    note_id: str,
    filename: str,
    content_type: str,
    size: int | None = None,
) -> str:
    """Request a presigned URL to upload a file attachment to a note.

    Args:
        note_id: Note UUID.
        filename: Attachment filename.
        content_type: MIME type.
        size: File size in bytes (recommended so the server can enforce quota).
    """
    body: dict = {"filename": filename, "content_type": content_type}
    if size is not None:
        body["size"] = size
    return json.dumps(await _request("POST", f"/notes/{note_id}/attachments", body=body))


@mcp.tool()
async def get_note_attachment(note_id: str, attachment_id: str) -> str:
    """Get a redirect URL to download a note attachment.

    Args:
        note_id: Note UUID.
        attachment_id: Attachment UUID.
    """
    return json.dumps(await _request("GET", f"/notes/{note_id}/attachments/{attachment_id}"))


@mcp.tool()
async def delete_note_attachment(note_id: str, attachment_id: str) -> str:
    """Delete a file attachment from a note.

    Args:
        note_id: Note UUID.
        attachment_id: Attachment UUID.
    """
    return json.dumps(await _request("DELETE", f"/notes/{note_id}/attachments/{attachment_id}"))


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_journal_entries(q: str | None = None) -> str:
    """List journal entries (summaries). Supports full-text search.

    Args:
        q: Optional search query.
    """
    params = {"q": q} if q else None
    return json.dumps(await _request("GET", "/journal", params=params))


@mcp.tool()
async def get_journal_entry(date: str) -> str:
    """Get journal entry for a specific date.

    Args:
        date: Date in YYYY-MM-DD format.
    """
    return json.dumps(await _request("GET", f"/journal/{date}"))


@mcp.tool()
async def upsert_journal_entry(
    date: str,
    title: str | None = None,
    body: str | None = None,
    mood: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Create or update a journal entry for a date.

    Args:
        date: Date in YYYY-MM-DD format.
        title: Entry title.
        body: Markdown content.
        mood: great, good, okay, bad, or terrible.
        tags: List of tags.
    """
    payload: dict = {}
    if title is not None:
        payload["title"] = title
    if body is not None:
        payload["body"] = body
    if mood is not None:
        payload["mood"] = mood
    if tags is not None:
        payload["tags"] = tags
    return json.dumps(await _request("PUT", f"/journal/{date}", body=payload))


@mcp.tool()
async def delete_journal_entry(date: str) -> str:
    """Delete a journal entry.

    Args:
        date: Date in YYYY-MM-DD format.
    """
    return json.dumps(await _request("DELETE", f"/journal/{date}"))


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_goals() -> str:
    """List all goals."""
    return json.dumps(await _request("GET", "/goals"))


@mcp.tool()
async def get_goal(goal_id: str) -> str:
    """Get a single goal.

    Args:
        goal_id: Goal UUID.
    """
    return json.dumps(await _request("GET", f"/goals/{goal_id}"))


@mcp.tool()
async def create_goal(
    title: str,
    description: str = "",
    target_date: str | None = None,
    status: str = "active",
    progress: int | None = None,
) -> str:
    """Create a goal.

    Args:
        title: Goal title (required).
        description: Goal description.
        target_date: Optional target date (YYYY-MM-DD).
        status: active, completed, or abandoned.
        progress: Completion percent (0-100). Defaults to 0.
    """
    payload: dict = {"title": title, "description": description, "status": status}
    if target_date:
        payload["target_date"] = target_date
    if progress is not None:
        payload["progress"] = progress
    return json.dumps(await _request("POST", "/goals", body=payload))


@mcp.tool()
async def update_goal(
    goal_id: str,
    title: str | None = None,
    description: str | None = None,
    target_date: str | None = None,
    status: str | None = None,
    progress: int | None = None,
) -> str:
    """Update a goal. Only provided fields are changed.

    Args:
        goal_id: Goal UUID.
        title: New title.
        description: New description.
        target_date: Target date (YYYY-MM-DD) or empty string to clear.
        status: active, completed, or abandoned.
        progress: Completion percent (0-100).
    """
    payload: dict = {}
    if title is not None:
        payload["title"] = title
    if description is not None:
        payload["description"] = description
    if target_date is not None:
        payload["target_date"] = target_date if target_date else None
    if status is not None:
        payload["status"] = status
    if progress is not None:
        payload["progress"] = progress
    return json.dumps(await _request("PUT", f"/goals/{goal_id}", body=payload))


@mcp.tool()
async def delete_goal(goal_id: str) -> str:
    """Delete a goal.

    Args:
        goal_id: Goal UUID.
    """
    return json.dumps(await _request("DELETE", f"/goals/{goal_id}"))


# ---------------------------------------------------------------------------
# Habits
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_habits() -> str:
    """List all habits with 30-day history, streaks, and today's status."""
    return json.dumps(await _request("GET", "/habits"))


@mcp.tool()
async def create_habit(
    name: str,
    notify_time: str | None = None,
    time_of_day: str | None = None,
) -> str:
    """Create a habit.

    Args:
        name: Habit name (required).
        notify_time: Optional daily reminder time in HH:MM (24h UTC). Empty string disables.
        time_of_day: When habit is typically done. One of: morning, afternoon, evening, anytime.
            Defaults to "anytime".
    """
    payload: dict = {"name": name}
    if notify_time is not None:
        payload["notify_time"] = notify_time
    if time_of_day is not None:
        payload["time_of_day"] = time_of_day
    return json.dumps(await _request("POST", "/habits", body=payload))


@mcp.tool()
async def update_habit(
    habit_id: str,
    name: str | None = None,
    notify_time: str | None = None,
    time_of_day: str | None = None,
) -> str:
    """Update a habit.

    Args:
        habit_id: Habit UUID.
        name: New name.
        notify_time: Reminder time (HH:MM UTC) or empty string to disable.
        time_of_day: morning, afternoon, evening, or anytime.
    """
    payload: dict = {}
    if name is not None:
        payload["name"] = name
    if notify_time is not None:
        payload["notify_time"] = notify_time
    if time_of_day is not None:
        payload["time_of_day"] = time_of_day
    return json.dumps(await _request("PUT", f"/habits/{habit_id}", body=payload))


@mcp.tool()
async def delete_habit(habit_id: str) -> str:
    """Delete a habit and all its logs.

    Args:
        habit_id: Habit UUID.
    """
    return json.dumps(await _request("DELETE", f"/habits/{habit_id}"))


@mcp.tool()
async def toggle_habit(habit_id: str, date: str | None = None) -> str:
    """Toggle habit completion for a date (defaults to today UTC).

    Args:
        habit_id: Habit UUID.
        date: Optional date (YYYY-MM-DD). Defaults to today.
    """
    params = {"date": date} if date else None
    return json.dumps(await _request("POST", f"/habits/{habit_id}/toggle", params=params))


# ---------------------------------------------------------------------------
# Health (Exercise)
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_health_logs() -> str:
    """List all exercise log summaries."""
    return json.dumps(await _request("GET", "/health"))


@mcp.tool()
async def get_health_log(date: str) -> str:
    """Get exercise log for a date.

    Args:
        date: Date in YYYY-MM-DD format.
    """
    return json.dumps(await _request("GET", f"/health/{date}"))


@mcp.tool()
async def upsert_health_log(
    date: str,
    exercises: list[dict] | None = None,
    notes: str | None = None,
) -> str:
    """Create or update an exercise log for a date.

    Args:
        date: Date in YYYY-MM-DD format.
        exercises: List of exercise objects. Each exercise supports:
            - name (str, required)
            - type ("strength" | "cardio" | "mobility", optional)
            - sets (list of {reps, weight}) for strength training
            - duration_min (number) for timed/cardio exercises
            - distance_km (number) for cardio
            - intensity (number 0-10, RPE)
            - muscle_groups (list of str)
        notes: Freeform notes.
    """
    payload: dict = {}
    if exercises is not None:
        payload["exercises"] = exercises
    if notes is not None:
        payload["notes"] = notes
    return json.dumps(await _request("PUT", f"/health/{date}", body=payload))


@mcp.tool()
async def delete_health_log(date: str) -> str:
    """Delete an exercise log.

    Args:
        date: Date in YYYY-MM-DD format.
    """
    return json.dumps(await _request("DELETE", f"/health/{date}"))


@mcp.tool()
async def get_health_summary(date_from: str | None = None, date_to: str | None = None) -> str:
    """Get rollup metrics (total volume, duration, distance, streak) across a date range.

    Args:
        date_from: Start date YYYY-MM-DD (default: 30 days ago).
        date_to: End date YYYY-MM-DD (default: today).
    """
    params: dict = {}
    if date_from: params["from"] = date_from
    if date_to:   params["to"]   = date_to
    return json.dumps(await _request("GET", "/health/summary", params=params))


@mcp.tool()
async def search_recent_exercises(
    q: str | None = None,
    days: int = 90,
    limit: int = 20,
) -> str:
    """Search recently logged exercises to re-use a previous workout.

    Returns distinct exercise names from the last N days with their most recent
    sets/duration/type/muscle_groups, so you can copy the payload into
    upsert_health_log to repeat the same workout.

    Args:
        q: Optional substring filter on exercise name (case-insensitive).
        days: Look back this many days (default 90, max 365).
        limit: Max distinct exercises to return (default 20, max 100).
    """
    params: dict = {"days": str(days), "limit": str(limit)}
    if q: params["q"] = q
    return json.dumps(await _request("GET", "/health/exercises/recent", params=params))


# ---------------------------------------------------------------------------
# Nutrition
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_nutrition_logs() -> str:
    """List all nutrition log summaries."""
    return json.dumps(await _request("GET", "/nutrition"))


@mcp.tool()
async def get_nutrition_log(date: str) -> str:
    """Get nutrition log for a date.

    Args:
        date: Date in YYYY-MM-DD format.
    """
    return json.dumps(await _request("GET", f"/nutrition/{date}"))


@mcp.tool()
async def upsert_nutrition_log(
    date: str,
    meals: list[dict] | None = None,
    notes: str | None = None,
) -> str:
    """Create or update a nutrition log for a date.

    Args:
        date: Date in YYYY-MM-DD format.
        meals: List of meal objects, each with name (str) and optional calories, protein, carbs, fat (numbers).
        notes: Freeform notes.
    """
    payload: dict = {}
    if meals is not None:
        payload["meals"] = meals
    if notes is not None:
        payload["notes"] = notes
    return json.dumps(await _request("PUT", f"/nutrition/{date}", body=payload))


@mcp.tool()
async def delete_nutrition_log(date: str) -> str:
    """Delete a nutrition log.

    Args:
        date: Date in YYYY-MM-DD format.
    """
    return json.dumps(await _request("DELETE", f"/nutrition/{date}"))


@mcp.tool()
async def get_nutrition_summary(date_from: str | None = None, date_to: str | None = None) -> str:
    """Get rollup macros (totals, per-day averages, streak) across a date range.

    Args:
        date_from: Start date YYYY-MM-DD (default: 30 days ago).
        date_to: End date YYYY-MM-DD (default: today).
    """
    params: dict = {}
    if date_from: params["from"] = date_from
    if date_to:   params["to"]   = date_to
    return json.dumps(await _request("GET", "/nutrition/summary", params=params))


@mcp.tool()
async def search_recent_meals(
    q: str | None = None,
    days: int = 90,
    limit: int = 20,
) -> str:
    """Search recently eaten meals to re-use a previous entry.

    Returns distinct meal names from the last N days with their most recent
    macros, so you can copy the payload into upsert_nutrition_log to log the
    same meal again.

    Args:
        q: Optional substring filter on meal name (case-insensitive).
        days: Look back this many days (default 90, max 365).
        limit: Max distinct meals to return (default 20, max 100).
    """
    params: dict = {"days": str(days), "limit": str(limit)}
    if q: params["q"] = q
    return json.dumps(await _request("GET", "/nutrition/meals/recent", params=params))


# ---------------------------------------------------------------------------
# Diagrams
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_diagrams() -> str:
    """List all diagram summaries (no elements or app_state)."""
    return json.dumps(await _request("GET", "/diagrams"))


@mcp.tool()
async def get_diagram(diagram_id: str) -> str:
    """Get a diagram with full elements and app_state.

    Args:
        diagram_id: Diagram UUID.
    """
    return json.dumps(await _request("GET", f"/diagrams/{diagram_id}"))


@mcp.tool()
async def create_diagram(
    title: str = "Untitled",
    elements: list[dict] | None = None,
    app_state: dict | None = None,
) -> str:
    """Create a diagram.

    Args:
        title: Diagram title (max 200 chars).
        elements: Excalidraw elements array.
        app_state: Excalidraw app state object.
    """
    payload: dict = {"title": title}
    if elements is not None:
        payload["elements"] = elements
    if app_state is not None:
        payload["app_state"] = app_state
    return json.dumps(await _request("POST", "/diagrams", body=payload))


@mcp.tool()
async def update_diagram(
    diagram_id: str,
    title: str | None = None,
    elements: list[dict] | None = None,
    app_state: dict | None = None,
) -> str:
    """Update a diagram.

    Args:
        diagram_id: Diagram UUID.
        title: New title.
        elements: New elements array.
        app_state: New app state.
    """
    payload: dict = {}
    if title is not None:
        payload["title"] = title
    if elements is not None:
        payload["elements"] = elements
    if app_state is not None:
        payload["app_state"] = app_state
    return json.dumps(await _request("PUT", f"/diagrams/{diagram_id}", body=payload))


@mcp.tool()
async def delete_diagram(diagram_id: str) -> str:
    """Delete a diagram.

    Args:
        diagram_id: Diagram UUID.
    """
    return json.dumps(await _request("DELETE", f"/diagrams/{diagram_id}"))


# ---------------------------------------------------------------------------
# Bookmarks
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_bookmarks(tag: str | None = None, q: str | None = None) -> str:
    """List bookmarks. Supports filtering by tag and full-text search.

    Args:
        tag: Filter by tag (case-insensitive).
        q: Search across title, URL, description, and note.
    """
    params: dict = {}
    if tag:
        params["tag"] = tag
    if q:
        params["q"] = q
    return json.dumps(await _request("GET", "/bookmarks", params=params or None))


@mcp.tool()
async def get_bookmark(bookmark_id: str) -> str:
    """Get a single bookmark.

    Args:
        bookmark_id: Bookmark UUID.
    """
    return json.dumps(await _request("GET", f"/bookmarks/{bookmark_id}"))


@mcp.tool()
async def create_bookmark(
    url: str,
    title: str | None = None,
    note: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Create a bookmark. The URL is scraped for title, favicon, and thumbnail.

    Args:
        url: HTTP or HTTPS URL (required, max 2048 chars).
        title: Override scraped title (max 500 chars).
        note: Freeform note (max 10,000 chars).
        tags: List of tags (max 20, each max 100 chars).
    """
    payload: dict = {"url": url}
    if title is not None:
        payload["title"] = title
    if note is not None:
        payload["note"] = note
    if tags is not None:
        payload["tags"] = tags
    return json.dumps(await _request("POST", "/bookmarks", body=payload))


@mcp.tool()
async def update_bookmark(
    bookmark_id: str,
    url: str | None = None,
    title: str | None = None,
    note: str | None = None,
    tags: list[str] | None = None,
    favourited: bool | None = None,
) -> str:
    """Update a bookmark. Only provided fields are changed.

    Args:
        bookmark_id: Bookmark UUID.
        url: New URL.
        title: New title.
        note: New note.
        tags: New tags list.
        favourited: Set favourite flag.
    """
    payload: dict = {}
    if url is not None:
        payload["url"] = url
    if title is not None:
        payload["title"] = title
    if note is not None:
        payload["note"] = note
    if tags is not None:
        payload["tags"] = tags
    if favourited is not None:
        payload["favourited"] = favourited
    return json.dumps(await _request("PUT", f"/bookmarks/{bookmark_id}", body=payload))


@mcp.tool()
async def delete_bookmark(bookmark_id: str) -> str:
    """Delete a bookmark.

    Args:
        bookmark_id: Bookmark UUID.
    """
    return json.dumps(await _request("DELETE", f"/bookmarks/{bookmark_id}"))


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_favorites() -> str:
    """List all saved favorites."""
    return json.dumps(await _request("GET", "/favorites"))


@mcp.tool()
async def create_favorite(
    url: str,
    title: str | None = None,
    feed_title: str | None = None,
    image: str | None = None,
    description: str | None = None,
    published: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Save an article as a favorite.

    Args:
        url: Article URL (required).
        title: Article title.
        feed_title: Source feed title.
        image: Image URL.
        description: Short description.
        published: Publish date (ISO 8601).
        tags: List of tags (max 20, each max 50 chars).
    """
    payload: dict = {"url": url}
    if title is not None:
        payload["title"] = title
    if feed_title is not None:
        payload["feed_title"] = feed_title
    if image is not None:
        payload["image"] = image
    if description is not None:
        payload["description"] = description
    if published is not None:
        payload["published"] = published
    if tags is not None:
        payload["tags"] = tags
    return json.dumps(await _request("POST", "/favorites", body=payload))


@mcp.tool()
async def update_favorite_tags(favorite_id: str, tags: list[str]) -> str:
    """Update tags on a favorite.

    Args:
        favorite_id: Favorite UUID.
        tags: New tags list (max 20, each max 50 chars).
    """
    return json.dumps(await _request("PATCH", f"/favorites/{favorite_id}", body={"tags": tags}))


@mcp.tool()
async def delete_favorite(favorite_id: str) -> str:
    """Remove a favorite.

    Args:
        favorite_id: Favorite UUID.
    """
    return json.dumps(await _request("DELETE", f"/favorites/{favorite_id}"))


# ---------------------------------------------------------------------------
# Feeds
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_feeds() -> str:
    """List subscribed RSS/Atom feeds."""
    return json.dumps(await _request("GET", "/feeds"))


@mcp.tool()
async def add_feed(url: str) -> str:
    """Subscribe to a feed. Accepts RSS/Atom URLs or pages with feed autodiscovery.

    Args:
        url: Feed or page URL.
    """
    return json.dumps(await _request("POST", "/feeds", body={"url": url}))


@mcp.tool()
async def delete_feed(feed_id: str) -> str:
    """Unsubscribe from a feed.

    Args:
        feed_id: Feed UUID.
    """
    return json.dumps(await _request("DELETE", f"/feeds/{feed_id}"))


@mcp.tool()
async def list_feed_articles(force: bool = False) -> str:
    """Fetch articles from all subscribed feeds. Cached for 30 minutes.

    Args:
        force: Force cache refresh.
    """
    params = {"force": "true"} if force else None
    return json.dumps(await _request("GET", "/feeds/articles", params=params))


@mcp.tool()
async def get_article_text(url: str) -> str:
    """Get plain text of an article (max 8000 chars).

    Args:
        url: Article URL.
    """
    return json.dumps(await _request("GET", "/feeds/article-text", params={"url": url}))


@mcp.tool()
async def get_read_articles() -> str:
    """Get list of read article URLs."""
    return json.dumps(await _request("GET", "/feeds/read"))


@mcp.tool()
async def mark_article_read(url: str) -> str:
    """Mark an article as read.

    Args:
        url: Article URL.
    """
    return json.dumps(await _request("POST", "/feeds/read", body={"url": url}))


# ---------------------------------------------------------------------------
# Finances
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_debts() -> str:
    """List all debts with computed payoff fields."""
    return json.dumps(await _request("GET", "/debts"))


@mcp.tool()
async def create_debt(
    name: str,
    type: str,
    balance: float,
    apr: float,
    monthly_payment: float,
    original_balance: float | None = None,
    notes: str | None = None,
) -> str:
    """Create a debt.

    Args:
        name: Debt name (max 200 chars).
        type: auto_loan, mortgage, credit_card, student_loan, personal_loan, line_of_credit, or other.
        balance: Current balance (> 0).
        apr: Annual percentage rate (>= 0).
        monthly_payment: Monthly payment amount (> 0).
        original_balance: Original balance (defaults to current balance).
        notes: Freeform notes (max 1000 chars).
    """
    payload: dict = {
        "name": name,
        "type": type,
        "balance": balance,
        "apr": apr,
        "monthly_payment": monthly_payment,
    }
    if original_balance is not None:
        payload["original_balance"] = original_balance
    if notes is not None:
        payload["notes"] = notes
    return json.dumps(await _request("POST", "/debts", body=payload))


@mcp.tool()
async def update_debt(
    debt_id: str,
    name: str | None = None,
    type: str | None = None,
    balance: float | None = None,
    apr: float | None = None,
    monthly_payment: float | None = None,
    original_balance: float | None = None,
    notes: str | None = None,
) -> str:
    """Update a debt.

    Args:
        debt_id: Debt UUID.
        name: New name.
        type: New type.
        balance: New balance.
        apr: New APR.
        monthly_payment: New monthly payment.
        original_balance: New original balance.
        notes: New notes.
    """
    payload: dict = {}
    if name is not None:
        payload["name"] = name
    if type is not None:
        payload["type"] = type
    if balance is not None:
        payload["balance"] = balance
    if apr is not None:
        payload["apr"] = apr
    if monthly_payment is not None:
        payload["monthly_payment"] = monthly_payment
    if original_balance is not None:
        payload["original_balance"] = original_balance
    if notes is not None:
        payload["notes"] = notes
    return json.dumps(await _request("PUT", f"/debts/{debt_id}", body=payload))


@mcp.tool()
async def delete_debt(debt_id: str) -> str:
    """Delete a debt.

    Args:
        debt_id: Debt UUID.
    """
    return json.dumps(await _request("DELETE", f"/debts/{debt_id}"))


@mcp.tool()
async def list_income() -> str:
    """List all income sources with computed monthly_amount."""
    return json.dumps(await _request("GET", "/income"))


@mcp.tool()
async def create_income(
    name: str,
    amount: float,
    frequency: str,
    notes: str | None = None,
) -> str:
    """Create an income source.

    Args:
        name: Income name (max 200 chars).
        amount: Amount (> 0).
        frequency: monthly, biweekly, weekly, or annual.
        notes: Freeform notes (max 1000 chars).
    """
    payload: dict = {"name": name, "amount": amount, "frequency": frequency}
    if notes is not None:
        payload["notes"] = notes
    return json.dumps(await _request("POST", "/income", body=payload))


@mcp.tool()
async def update_income(
    income_id: str,
    name: str | None = None,
    amount: float | None = None,
    frequency: str | None = None,
    notes: str | None = None,
) -> str:
    """Update an income source.

    Args:
        income_id: Income UUID.
        name: New name.
        amount: New amount.
        frequency: New frequency.
        notes: New notes.
    """
    payload: dict = {}
    if name is not None:
        payload["name"] = name
    if amount is not None:
        payload["amount"] = amount
    if frequency is not None:
        payload["frequency"] = frequency
    if notes is not None:
        payload["notes"] = notes
    return json.dumps(await _request("PUT", f"/income/{income_id}", body=payload))


@mcp.tool()
async def delete_income(income_id: str) -> str:
    """Delete an income source.

    Args:
        income_id: Income UUID.
    """
    return json.dumps(await _request("DELETE", f"/income/{income_id}"))


@mcp.tool()
async def list_fixed_expenses() -> str:
    """List all fixed expenses with computed monthly_amount."""
    return json.dumps(await _request("GET", "/fixed-expenses"))


@mcp.tool()
async def create_fixed_expense(
    name: str,
    amount: float,
    frequency: str,
    category: str,
    due_day: int | None = None,
    notes: str | None = None,
) -> str:
    """Create a fixed expense.

    Args:
        name: Expense name (max 200 chars).
        amount: Amount (> 0).
        frequency: monthly, biweekly, weekly, or annual.
        category: housing, utilities, subscriptions, insurance, food, transport, healthcare, or other.
        due_day: Day of month (1-31) payment is due.
        notes: Freeform notes (max 1000 chars).
    """
    payload: dict = {"name": name, "amount": amount, "frequency": frequency, "category": category}
    if due_day is not None:
        payload["due_day"] = due_day
    if notes is not None:
        payload["notes"] = notes
    return json.dumps(await _request("POST", "/fixed-expenses", body=payload))


@mcp.tool()
async def update_fixed_expense(
    expense_id: str,
    name: str | None = None,
    amount: float | None = None,
    frequency: str | None = None,
    category: str | None = None,
    due_day: int | None = None,
    notes: str | None = None,
) -> str:
    """Update a fixed expense.

    Args:
        expense_id: Expense UUID.
        name: New name.
        amount: New amount.
        frequency: New frequency.
        category: New category.
        due_day: New due day (1-31).
        notes: New notes.
    """
    payload: dict = {}
    if name is not None:
        payload["name"] = name
    if amount is not None:
        payload["amount"] = amount
    if frequency is not None:
        payload["frequency"] = frequency
    if category is not None:
        payload["category"] = category
    if due_day is not None:
        payload["due_day"] = due_day
    if notes is not None:
        payload["notes"] = notes
    return json.dumps(await _request("PUT", f"/fixed-expenses/{expense_id}", body=payload))


@mcp.tool()
async def delete_fixed_expense(expense_id: str) -> str:
    """Delete a fixed expense.

    Args:
        expense_id: Expense UUID.
    """
    return json.dumps(await _request("DELETE", f"/fixed-expenses/{expense_id}"))


@mcp.tool()
async def get_finances_summary() -> str:
    """Get financial summary with all debts, income, expenses, and computed totals (monthly income, outflow, net cash flow)."""
    return json.dumps(await _request("GET", "/finances/summary"))


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_settings() -> str:
    """Get user settings."""
    return json.dumps(await _request("GET", "/settings"))


@mcp.tool()
async def update_settings(
    dark_mode: bool | None = None,
    ntfy_url: str | None = None,
    autosave_seconds: int | None = None,
    timezone: str | None = None,
    display_name: str | None = None,
    pal_name: str | None = None,
    profile_inference_hours: int | None = None,
    home_finances_widget: bool | None = None,
) -> str:
    """Update user settings. Only provided fields are changed.

    Args:
        dark_mode: Enable/disable dark mode.
        ntfy_url: ntfy push notification endpoint URL (HTTPS only, no private addresses).
        autosave_seconds: Auto-save interval (60, 120, or 300).
        timezone: IANA timezone string (e.g. America/New_York).
        display_name: Name to show in UI greetings.
        pal_name: Custom name for the AI assistant (default "Pip").
        profile_inference_hours: Hours between watcher profile-inference runs.
        home_finances_widget: Show finances widget on the home dashboard.
    """
    payload: dict = {}
    if dark_mode is not None:
        payload["dark_mode"] = dark_mode
    if ntfy_url is not None:
        payload["ntfy_url"] = ntfy_url
    if autosave_seconds is not None:
        payload["autosave_seconds"] = autosave_seconds
    if timezone is not None:
        payload["timezone"] = timezone
    if display_name is not None:
        payload["display_name"] = display_name
    if pal_name is not None:
        payload["pal_name"] = pal_name
    if profile_inference_hours is not None:
        payload["profile_inference_hours"] = profile_inference_hours
    if home_finances_widget is not None:
        payload["home_finances_widget"] = home_finances_widget
    return json.dumps(await _request("PUT", "/settings", body=payload))


@mcp.tool()
async def test_notification(ntfy_url: str | None = None) -> str:
    """Send a test push notification.

    Args:
        ntfy_url: Optional URL to test. If omitted, uses the saved setting.
    """
    body = {"ntfy_url": ntfy_url} if ntfy_url else None
    return json.dumps(await _request("POST", "/settings/test-notification", body=body))


# ---------------------------------------------------------------------------
# Assistant (Pip)
# ---------------------------------------------------------------------------


@mcp.tool()
async def chat_with_assistant(
    message: str,
    model: str | None = None,
    local_date: str | None = None,
    no_history: bool = False,
    conversation_id: str | None = None,
) -> str:
    """Send a message to the AI assistant (Pip). The assistant can read/write tasks, notes, habits, goals, journal, nutrition, and exercise data.

    Args:
        message: User message.
        model: Bedrock model ID. Options: us.amazon.nova-lite-v1:0 (default), us.amazon.nova-pro-v1:0.
        local_date: Current date (YYYY-MM-DD) for context.
        no_history: Skip loading prior conversation history (one-shot mode). Does not persist the turn.
        conversation_id: Optional thread UUID. If omitted and no_history is false, a new thread is auto-created.
            The response includes `conversation_id`; pass it back to continue the same thread.
    """
    payload: dict = {"message": message}
    if model is not None:
        payload["model"] = model
    if local_date is not None:
        payload["local_date"] = local_date
    if no_history:
        payload["no_history"] = True
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id
    return json.dumps(await _request("POST", "/assistant/chat", body=payload))


@mcp.tool()
async def list_conversations() -> str:
    """List saved AI assistant conversation threads (metadata only, ordered by most recent update)."""
    return json.dumps(await _request("GET", "/assistant/conversations"))


@mcp.tool()
async def create_conversation(title: str = "New chat") -> str:
    """Create an empty assistant conversation thread.

    Args:
        title: Thread title (max 200 chars).
    """
    return json.dumps(await _request("POST", "/assistant/conversations", body={"title": title}))


@mcp.tool()
async def get_conversation(conversation_id: str) -> str:
    """Get metadata + full message history for one assistant conversation thread.

    Args:
        conversation_id: Thread UUID.
    """
    return json.dumps(await _request("GET", f"/assistant/conversations/{conversation_id}"))


@mcp.tool()
async def rename_conversation(conversation_id: str, title: str) -> str:
    """Rename an assistant conversation thread.

    Args:
        conversation_id: Thread UUID.
        title: New title (max 200 chars).
    """
    return json.dumps(await _request("PATCH", f"/assistant/conversations/{conversation_id}", body={"title": title}))


@mcp.tool()
async def delete_conversation(conversation_id: str) -> str:
    """Delete an assistant conversation thread and all of its messages.

    Args:
        conversation_id: Thread UUID.
    """
    return json.dumps(await _request("DELETE", f"/assistant/conversations/{conversation_id}"))


@mcp.tool()
async def get_assistant_history() -> str:
    """Get conversation history with the AI assistant (last 20 messages, 30-day TTL)."""
    return json.dumps(await _request("GET", "/assistant/history"))


@mcp.tool()
async def clear_assistant_history() -> str:
    """Clear conversation history with the AI assistant."""
    return json.dumps(await _request("DELETE", "/assistant/history"))


@mcp.tool()
async def get_assistant_usage() -> str:
    """Get Bedrock token usage statistics per model."""
    return json.dumps(await _request("GET", "/assistant/usage"))


@mcp.tool()
async def get_assistant_memory() -> str:
    """Get assistant memory (master context, facts, profile, AI analysis)."""
    return json.dumps(await _request("GET", "/assistant/memory"))


@mcp.tool()
async def update_assistant_context(master_context: str) -> str:
    """Update the assistant's master context.

    Args:
        master_context: Multi-sentence summary for the assistant to remember.
    """
    return json.dumps(await _request("PUT", "/assistant/memory", body={"master_context": master_context}))


@mcp.tool()
async def upsert_assistant_fact(key: str, value: str) -> str:
    """Create or update a memory fact for the assistant.

    Args:
        key: Snake_case fact key (cannot start with __).
        value: Fact value.
    """
    return json.dumps(await _request("PUT", f"/assistant/memory/facts/{key}", body={"value": value}))


@mcp.tool()
async def delete_assistant_fact(key: str) -> str:
    """Delete a memory fact.

    Args:
        key: Fact key.
    """
    return json.dumps(await _request("DELETE", f"/assistant/memory/{key}"))


@mcp.tool()
async def get_assistant_profile() -> str:
    """Get user profile used by the assistant."""
    return json.dumps(await _request("GET", "/assistant/profile"))


@mcp.tool()
async def update_assistant_profile(
    name: str | None = None,
    occupation: str | None = None,
    summary: str | None = None,
) -> str:
    """Update the user profile for the assistant. At least one field required.

    Args:
        name: User's name.
        occupation: User's occupation.
        summary: Short summary about the user.
    """
    payload: dict = {}
    if name is not None:
        payload["name"] = name
    if occupation is not None:
        payload["occupation"] = occupation
    if summary is not None:
        payload["summary"] = summary
    return json.dumps(await _request("PUT", "/assistant/profile", body=payload))


@mcp.tool()
async def analyze_assistant_profile() -> str:
    """Generate an AI analysis of the user profile and stored facts."""
    return json.dumps(await _request("POST", "/assistant/profile/analyze"))


# ---------------------------------------------------------------------------
# Home / Admin
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_costs() -> str:
    """Get AWS cost breakdown for the current month (grouped by service)."""
    return json.dumps(await _request("GET", "/home/costs"))


@mcp.tool()
async def get_admin_stats() -> str:
    """Get admin statistics (DynamoDB table sizes, S3 bucket usage)."""
    return json.dumps(await _request("GET", "/admin/stats"))


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@mcp.tool()
async def export_data() -> str:
    """Download all user data as a ZIP file (Markdown files organised by feature). Returns the raw response which may be binary."""
    return json.dumps(await _request("GET", "/export"))


# ---------------------------------------------------------------------------
# Tokens
#
# NOTE: Token management endpoints are JWT-only on the server side.
# When this MCP server authenticates with a PAT (MEMOIRE_PAT), these
# tools will return a 403 error. They are included for completeness
# and will work if a future release adds JWT-based MCP authentication.
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_tokens() -> str:
    """List personal access tokens (metadata only, no secrets).

    WARNING: This endpoint requires JWT authentication. It will return 403
    when the MCP server is configured with a PAT (MEMOIRE_PAT).
    """
    return json.dumps(await _request("GET", "/tokens"))


@mcp.tool()
async def create_token(name: str) -> str:
    """Create a personal access token. The plaintext token (pat_...) is returned once and never shown again.

    WARNING: This endpoint requires JWT authentication. It will return 403
    when the MCP server is configured with a PAT (MEMOIRE_PAT).

    Args:
        name: Token name (max 100 chars).
    """
    return json.dumps(await _request("POST", "/tokens", body={"name": name}))


@mcp.tool()
async def revoke_token(token_id: str) -> str:
    """Revoke a personal access token.

    WARNING: This endpoint requires JWT authentication. It will return 403
    when the MCP server is configured with a PAT (MEMOIRE_PAT).

    Args:
        token_id: Token UUID.
    """
    return json.dumps(await _request("DELETE", f"/tokens/{token_id}"))


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
