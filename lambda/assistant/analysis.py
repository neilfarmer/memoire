"""Generate a data-driven AI profile analysis from the user's app data."""

import logging
import os
from datetime import date, datetime, timezone

import boto3
import db
import memory as mem
from chat import _clean_reply

logger = logging.getLogger(__name__)

MODEL_ID = os.environ.get("ASSISTANT_MODEL_ID", "us.amazon.nova-lite-v1:0")

TASKS_TABLE   = os.environ["TASKS_TABLE"]
NOTES_TABLE   = os.environ["NOTES_TABLE"]
HABITS_TABLE  = os.environ["HABITS_TABLE"]
GOALS_TABLE   = os.environ["GOALS_TABLE"]
JOURNAL_TABLE = os.environ["JOURNAL_TABLE"]

_bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))


def generate_analysis(user_id: str) -> dict:
    """Fetch all user data, call Bedrock, persist and return the analysis."""
    tasks   = db.query_by_user(db.get_table(TASKS_TABLE),   user_id)
    notes   = db.query_by_user(db.get_table(NOTES_TABLE),   user_id)
    habits  = db.query_by_user(db.get_table(HABITS_TABLE),  user_id)
    goals   = db.query_by_user(db.get_table(GOALS_TABLE),   user_id)
    journal = sorted(
        db.query_by_user(db.get_table(JOURNAL_TABLE), user_id),
        key=lambda e: e.get("entry_date", ""),
        reverse=True,
    )[:12]

    profile       = mem.load_profile(user_id)
    facts, master = mem.load_memory(user_id)

    today        = date.today().strftime("%A, %B %d, %Y")
    done_tasks   = [t for t in tasks if t.get("status") == "done"]
    active_tasks = [t for t in tasks if t.get("status") in ("todo", "in_progress")]
    high_pri     = [t for t in active_tasks if t.get("priority") == "high"]

    task_titles = "; ".join(t.get("title", "") for t in tasks[:25]) or "none"
    note_titles = "; ".join(n.get("title", "") for n in notes[:15])  or "none"
    habit_names = "; ".join(h.get("name",  "") for h in habits)      or "none"
    goal_titles = "; ".join(
        g.get("title", "") for g in goals if g.get("status") != "abandoned"
    ) or "none"

    journal_lines = []
    for e in journal[:8]:
        mood = e.get("mood", "")
        body = (e.get("body", "") or "")[:250]
        journal_lines.append(f"[{e.get('entry_date', '')} mood:{mood}] {body}")
    journal_text = "\n".join(journal_lines) or "none"

    facts_text = "\n".join(f"- {k}: {v}" for k, v in facts.items()) if facts else "none"

    prompt = (
        f"Today is {today}.\n\n"
        f"You are generating a personal profile analysis for a user of a productivity app. "
        f"Be warm, specific, and insightful. Identify real patterns — not generic observations.\n\n"
        f"Self-reported profile:\n"
        f"- Name: {profile.get('name') or 'not provided'}\n"
        f"- Occupation: {profile.get('occupation') or 'not provided'}\n"
        f"- About: {profile.get('summary') or 'not provided'}\n\n"
        f"Remembered facts from conversations:\n{facts_text}\n\n"
        f"Running context: {master or 'none'}\n\n"
        f"Tasks ({len(active_tasks)} active, {len(done_tasks)} completed, "
        f"{len(high_pri)} high-priority):\n{task_titles}\n\n"
        f"Notes: {note_titles}\n\n"
        f"Habits: {habit_names}\n\n"
        f"Goals: {goal_titles}\n\n"
        f"Recent journal entries:\n{journal_text}\n\n"
        f"Write a 4-6 sentence profile analysis covering: work style, priorities, recurring themes, "
        f"and what this person seems to value or be working toward. "
        f"Be personal and specific to this data. Plain text only — no headings or bullet points."
    )

    resp = _bedrock.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 500},
    )
    analysis     = _clean_reply(resp["output"]["message"]["content"][0]["text"].strip())
    generated_at = datetime.now(timezone.utc).isoformat()
    mem.save_ai_analysis(user_id, analysis)
    return {"analysis": analysis, "generated_at": generated_at}
