"""Build a ZIP archive of all user data as human-readable files."""

import json
import os
import re
import tempfile
import uuid
import zipfile
from datetime import date

import boto3
from boto3.dynamodb.conditions import Key
import db

TASKS_TABLE        = os.environ["TASKS_TABLE"]
JOURNAL_TABLE      = os.environ["JOURNAL_TABLE"]
NOTES_TABLE        = os.environ["NOTES_TABLE"]
FOLDERS_TABLE      = os.environ["FOLDERS_TABLE"]
HEALTH_TABLE       = os.environ["HEALTH_TABLE"]
GOALS_TABLE        = os.environ["GOALS_TABLE"]
HABITS_TABLE       = os.environ["HABITS_TABLE"]
HABIT_LOGS_TABLE   = os.environ["HABIT_LOGS_TABLE"]
FRONTEND_BUCKET    = os.environ["FRONTEND_BUCKET"]

s3 = boto3.client("s3")

PRIORITY_SYMBOL = {"high": "!!!", "medium": "!!", "low": "!"}
STATUS_LABEL    = {"todo": "Todo", "in_progress": "In Progress", "done": "Done"}
CHECKBOX        = {"todo": "[ ]", "in_progress": "[-]", "done": "[x]"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_name(name: str) -> str:
    name = name.strip() or "Untitled"
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    return name[:80]


def _frontmatter(**fields) -> str:
    lines = ["---"]
    for k, v in fields.items():
        if v is not None and v != "" and v != []:
            if isinstance(v, list):
                lines.append(f"{k}: {', '.join(str(i) for i in v)}")
            else:
                lines.append(f"{k}: {v}")
    lines.append("---\n")
    return "\n".join(lines)


def _fetch_s3(key: str) -> bytes | None:
    try:
        resp = s3.get_object(Bucket=FRONTEND_BUCKET, Key=key)
        return resp["Body"].read()
    except Exception:
        return None


# ── Tasks ─────────────────────────────────────────────────────────────────────

def _tasks_section(tasks: list[dict], heading_level: int = 2) -> str:
    """Render a list of tasks grouped by status. heading_level is the level
    used for status sub-headings (H2 by default; H3 when nested under tag
    sections so the document outline stays clean)."""
    grouped: dict[str, list] = {"todo": [], "in_progress": [], "done": []}
    for t in tasks:
        grouped.setdefault(t.get("status", "todo"), []).append(t)

    hashes = "#" * max(1, min(heading_level, 6))
    lines: list[str] = []
    for status in ("todo", "in_progress", "done"):
        bucket = grouped.get(status, [])
        if not bucket:
            continue
        lines.append(f"{hashes} {STATUS_LABEL[status]}\n")
        for t in sorted(bucket, key=lambda x: x.get("created_at", "")):
            cb       = CHECKBOX[status]
            priority = PRIORITY_SYMBOL.get(t.get("priority", "medium"), "!!")
            title    = t.get("title", "Untitled")
            lines.append(f"- {cb} {priority} {title}")
            if t.get("due_date"):
                lines.append(f"  Due: {t['due_date']}")
            if t.get("scheduled_start"):
                dur = t.get("duration_minutes") or 30
                lines.append(f"  Scheduled: {t['scheduled_start']} ({dur} min)")
            if t.get("recurrence_rule"):
                rr = t["recurrence_rule"]
                lines.append(f"  Recurs: {rr.get('freq', '?')} every {rr.get('interval', 1)}")
            if t.get("reschedule_count"):
                lines.append(f"  Rescheduled {t['reschedule_count']} time(s)")
            if t.get("description"):
                lines.append(f"  {t['description']}")
            lines.append("")
    return "\n".join(lines)


def _tasks_markdown(tasks: list[dict]) -> str:
    if not tasks:
        return "# Tasks\n\nNo tasks found.\n"

    by_tag: dict[str, list] = {}
    untagged: list = []
    for t in tasks:
        tags = t.get("tags") or []
        if not tags:
            untagged.append(t)
            continue
        for tag in tags:
            by_tag.setdefault(tag, []).append(t)

    lines = ["# Tasks\n"]
    for tag in sorted(by_tag.keys(), key=str.lower):
        lines.append(f"## {tag}\n")
        lines.append(_tasks_section(by_tag[tag], heading_level=3))
    if untagged:
        lines.append("## Untagged\n")
        lines.append(_tasks_section(untagged, heading_level=3))
    return "\n".join(lines)


# ── Journal ───────────────────────────────────────────────────────────────────

def _journal_file(entry: dict) -> tuple[str, str]:
    entry_date = entry.get("entry_date", "unknown")
    filename   = f"{_safe_name(entry_date)}.md"

    fm = _frontmatter(
        date = entry_date,
        mood = entry.get("mood") or None,
        tags = entry.get("tags") or None,
    )
    title = entry.get("title", "").strip()
    body  = entry.get("body", "")

    content = fm
    if title:
        content += f"# {title}\n\n"
    content += body + "\n"

    return filename, content


# ── Notes ─────────────────────────────────────────────────────────────────────

def _build_folder_paths(folders: list[dict]) -> dict[str, str]:
    by_id = {f["folder_id"]: f for f in folders}

    def _path(folder_id: str, visited: set) -> str:
        if folder_id in visited:
            return _safe_name(by_id[folder_id].get("name", "Unknown"))
        visited.add(folder_id)
        f = by_id.get(folder_id)
        if not f:
            return "Unknown"
        name   = _safe_name(f.get("name", "Untitled"))
        parent = f.get("parent_id")
        if parent and parent in by_id:
            return _path(parent, visited) + "/" + name
        return name

    return {fid: _path(fid, set()) for fid in by_id}


def _note_files(note: dict, zip_folder: str) -> list[tuple[str, bytes]]:
    """
    Return a list of (zip_path, bytes) pairs for a note and all its assets.
    Images are fetched from S3 and bundled; src paths in the markdown are
    rewritten to relative paths.  Attachments are downloaded and placed in
    an attachments/ sub-folder.
    """
    title    = note.get("title", "").strip() or "Untitled"
    filename = _safe_name(title) + ".md"

    attachments = note.get("attachments") or []
    attach_names = [a.get("name", "file") for a in attachments]

    fm = _frontmatter(
        tags        = note.get("tags") or None,
        created_at  = note.get("created_at") or None,
        updated_at  = note.get("updated_at") or None,
        attachments = attach_names or None,
    )
    body = note.get("body", "")

    # ── Resolve pasted images ─────────────────────────────────────────────────
    files: list[tuple[str, bytes]] = []
    image_counter = [0]

    def _replace_image(m: re.Match) -> str:
        s3_key  = m.group(1)                         # note-images/uid/uuid.ext
        parts   = s3_key.split("/")
        ext     = parts[-1].rsplit(".", 1)[-1] if "." in parts[-1] else "png"
        img_name = f"image_{image_counter[0]:03d}.{ext}"
        image_counter[0] += 1

        data = _fetch_s3(s3_key)
        if data:
            files.append((f"{zip_folder}/images/{img_name}", data))
            return f"![](images/{img_name})"
        # If fetch failed, remove broken reference
        return ""

    body = re.sub(r"!\[[^\]]*\]\((note-images/[^)]+)\)", _replace_image, body)

    content = (fm + f"# {title}\n\n" + body + "\n").encode()
    files.append((f"{zip_folder}/{filename}", content))

    # ── Attachments ───────────────────────────────────────────────────────────
    for att in attachments:
        key      = att.get("key", "")
        att_name = _safe_name(att.get("name", "file"))
        if not key:
            continue
        data = _fetch_s3(key)
        if data:
            files.append((f"{zip_folder}/attachments/{_safe_name(title)}/{att_name}", data))

    return files


# ── Health ────────────────────────────────────────────────────────────────────

def _health_file(log: dict) -> tuple[str, str]:
    log_date = log.get("log_date", "unknown")
    filename = f"{_safe_name(log_date)}.md"

    exercises = log.get("exercises") or []
    lines = [f"# Workout — {log_date}\n"]

    for ex in exercises:
        name = ex.get("name", "Exercise")
        lines.append(f"## {name}\n")
        for i, s in enumerate(ex.get("sets") or [], 1):
            reps   = s.get("reps")
            weight = s.get("weight")
            if reps is not None and weight is not None:
                lines.append(f"- Set {i}: {reps} reps × {weight} lbs")
            elif reps is not None:
                lines.append(f"- Set {i}: {reps} reps")
        dur = ex.get("duration_min")
        if dur:
            lines.append(f"- Duration: {dur} min")
        lines.append("")

    notes = log.get("notes", "").strip()
    if notes:
        lines.append(f"**Notes:** {notes}\n")

    return filename, "\n".join(lines)


# ── Nutrition ─────────────────────────────────────────────────────────────────

def _nutrition_file(log: dict) -> tuple[str, str]:
    log_date = log.get("log_date", "unknown")
    filename = f"{_safe_name(log_date)}.md"

    meals = log.get("meals") or []
    total_cal  = sum(m.get("calories")  or 0 for m in meals)
    total_prot = sum(m.get("protein_g") or 0 for m in meals)
    total_carb = sum(m.get("carbs_g")   or 0 for m in meals)
    total_fat  = sum(m.get("fat_g")     or 0 for m in meals)

    lines = [f"# Nutrition — {log_date}\n"]
    if total_cal:
        lines.append(f"**Totals:** {total_cal} cal | {total_prot}g protein | {total_carb}g carbs | {total_fat}g fat\n")

    for meal in meals:
        name = meal.get("name", "Meal")
        cal  = meal.get("calories")
        prot = meal.get("protein_g")
        carb = meal.get("carbs_g")
        fat  = meal.get("fat_g")
        macros = " | ".join(filter(None, [
            f"{cal} cal"   if cal  is not None else None,
            f"{prot}g protein" if prot is not None else None,
            f"{carb}g carbs"   if carb is not None else None,
            f"{fat}g fat"      if fat  is not None else None,
        ]))
        lines.append(f"- **{name}**" + (f": {macros}" if macros else ""))

    notes = log.get("notes", "").strip()
    if notes:
        lines.append(f"\n**Notes:** {notes}")

    return filename, "\n".join(lines) + "\n"


# ── Goals ─────────────────────────────────────────────────────────────────────

def _goals_markdown(goals: list[dict]) -> str:
    if not goals:
        return "# Goals\n\nNo goals found.\n"

    grouped: dict[str, list] = {"active": [], "completed": [], "abandoned": []}
    for g in goals:
        grouped.setdefault(g.get("status", "active"), []).append(g)

    label = {"active": "Active", "completed": "Completed", "abandoned": "Abandoned"}
    lines = ["# Goals\n"]
    for status in ("active", "completed", "abandoned"):
        bucket = grouped.get(status, [])
        if not bucket:
            continue
        lines.append(f"## {label[status]}\n")
        for g in sorted(bucket, key=lambda x: x.get("created_at", "")):
            lines.append(f"- **{g.get('title', 'Untitled')}**")
            if g.get("target_date"):
                lines.append(f"  Target: {g['target_date']}")
            if g.get("description"):
                lines.append(f"  {g['description']}")
            lines.append("")

    return "\n".join(lines)


# ── Habits ────────────────────────────────────────────────────────────────────

def _habits_markdown(habits: list[dict], all_logs: list[dict]) -> str:
    if not habits:
        return "# Habits\n\nNo habits found.\n"

    logs_by_habit: dict[str, list[str]] = {}
    for log in all_logs:
        hid = log.get("habit_id", "")
        logs_by_habit.setdefault(hid, []).append(log.get("log_date", ""))

    lines = ["# Habits\n"]
    for habit in sorted(habits, key=lambda h: h.get("created_at", "")):
        name     = habit.get("name", "Untitled")
        notify   = habit.get("notify_time", "")
        created  = habit.get("created_at", "")
        hid      = habit.get("habit_id", "")
        log_dates = sorted(logs_by_habit.get(hid, []))

        lines.append(f"## {name}\n")
        if notify:
            lines.append(f"- Reminder: {notify}")
        if created:
            lines.append(f"- Tracking since: {created}")
        if log_dates:
            lines.append(f"- Completions ({len(log_dates)} total):")
            for d in log_dates:
                lines.append(f"  - {d}")
        lines.append("")

    return "\n".join(lines)


# ── Main builder ──────────────────────────────────────────────────────────────

def build_export(user_id: str) -> dict:
    tasks        = db.query_by_user(db.get_table(TASKS_TABLE),        user_id)
    entries      = db.query_by_user(db.get_table(JOURNAL_TABLE),      user_id)
    notes        = db.query_by_user(db.get_table(NOTES_TABLE),        user_id)
    folders      = db.query_by_user(db.get_table(FOLDERS_TABLE),      user_id)
    health       = db.query_by_user(db.get_table(HEALTH_TABLE),       user_id)
    goals        = db.query_by_user(db.get_table(GOALS_TABLE),        user_id)
    habits       = db.query_by_user(db.get_table(HABITS_TABLE),       user_id)

    # Fetch all habit logs for the user with pagination
    habit_logs: list[dict] = []
    logs_table = db.get_table(HABIT_LOGS_TABLE)
    for habit in habits:
        params: dict = {
            "KeyConditionExpression":
                Key("user_id").eq(user_id) &
                Key("log_id").begins_with(f"{habit['habit_id']}#")
        }
        while True:
            resp = logs_table.query(**params)
            habit_logs.extend(resp.get("Items", []))
            if "LastEvaluatedKey" not in resp:
                break
            params["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    folder_paths = _build_folder_paths(folders)

    today = date.today().isoformat()
    export_key = f"exports/{user_id}/{today}-{uuid.uuid4().hex[:8]}.zip"
    fd, tmp_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)

    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            root = f"memoire-export-{today}"

            # ── tasks/tasks.md ────────────────────────────────────────────────
            zf.writestr(f"{root}/tasks/tasks.md", _tasks_markdown(tasks))

            # ── journal/YYYY-MM-DD.md ─────────────────────────────────────────
            for entry in sorted(entries, key=lambda e: e.get("entry_date", "")):
                filename, content = _journal_file(entry)
                zf.writestr(f"{root}/journal/{filename}", content)

            # ── notes/{folder}/{title}.md + images/ + attachments/ ────────────
            seen: dict[str, int] = {}
            for note in sorted(notes, key=lambda n: n.get("created_at", "")):
                folder_id   = note.get("folder_id")
                folder_path = folder_paths.get(folder_id, "Uncategorized") if folder_id else "Uncategorized"
                zip_folder  = f"{root}/notes/{folder_path}"

                # Deduplicate note filename within folder
                base_name = _safe_name(note.get("title", "").strip() or "Untitled") + ".md"
                path_key  = f"{folder_path}/{base_name}"
                if path_key in seen:
                    seen[path_key] += 1
                    base = base_name[:-3]
                    base_name = f"{base} ({seen[path_key]}).md"
                else:
                    seen[path_key] = 0

                for zip_path, data in _note_files(note, zip_folder):
                    # If the note md was deduplicated, rename it in the output too
                    if zip_path.endswith(".md") and not zip_path.endswith(base_name):
                        zip_path = zip_path.rsplit("/", 1)[0] + "/" + base_name
                    zf.writestr(zip_path, data)

            # ── health/YYYY-MM-DD.md ──────────────────────────────────────────
            for log in sorted(health, key=lambda x: x.get("log_date", "")):
                filename, content = _health_file(log)
                zf.writestr(f"{root}/health/{filename}", content)

            # ── goals/goals.md ────────────────────────────────────────────────
            zf.writestr(f"{root}/goals/goals.md", _goals_markdown(goals))

            # ── habits/habits.md ──────────────────────────────────────────────
            zf.writestr(f"{root}/habits/habits.md", _habits_markdown(habits, habit_logs))

        s3.upload_file(tmp_path, FRONTEND_BUCKET, export_key)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    url = s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": FRONTEND_BUCKET,
            "Key":    export_key,
            "ResponseContentDisposition": f'attachment; filename="memoire-export-{today}.zip"',
            "ResponseContentType":        "application/zip",
        },
        ExpiresIn=300,  # 5 minutes
    )

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"url": url}),
    }
