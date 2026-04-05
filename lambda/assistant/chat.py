"""Main Bedrock chat logic for the AI assistant."""

import json
import logging
import os
import re
from datetime import date

import boto3

import memory as mem
from tools import TOOL_SPECS, handle_tool
from response import ok, server_error

logger = logging.getLogger(__name__)

MODEL_ID   = os.environ.get("ASSISTANT_MODEL_ID", "us.amazon.nova-lite-v1:0")
MAX_TOKENS = 1024
MAX_LOOPS  = 6

_ALLOWED_MODELS = {
    "us.amazon.nova-lite-v1:0",
    "us.amazon.nova-pro-v1:0",
}

_bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))


def _clean_reply(text: str) -> str:
    """Strip XML reasoning/wrapper tags some models emit (e.g. Nova Lite)."""
    # Remove <thinking>...</thinking> blocks
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL)
    # Unwrap <response>...</response> if present
    m = re.search(r"<response>(.*?)</response>", text, re.DOTALL)
    if m:
        text = m.group(1)
    return text.strip()


_DEFAULT_SYSTEM_PROMPT = """\
You are a warm, helpful personal assistant for Memoire, a personal productivity app.
You help the user manage their tasks, notes, habits, goals, and journal entries.
Today is {today}.

What you know about the user:
{memory_text}

CRITICAL RULES — you must follow these exactly:
1. ALWAYS call the appropriate tool before confirming any action. NEVER claim to have created, updated, listed, deleted, or completed anything without first invoking the tool. The tools are the only way actions actually happen — if you don't call a tool, nothing changes.
2. Do NOT narrate what you are about to do. Just call the tool immediately.
3. After the tool returns a result, confirm briefly in 1–2 sentences.
4. If you learn something meaningful about the user (preferences, routines, goals), call remember_fact.
5. Be concise and friendly. When listing items, keep it brief.
6. For delete/complete/toggle operations, always call list_* first to find the correct ID, then call the action tool.
7. ROUTING RULES — use the correct tool for the domain:
   - Food, eating, calories, macros, meals, "food journal", diet → log_meal (NOT create_journal_entry)
   - Workouts, exercise, gym, running, lifting, physical activity → log_exercise (NOT create_journal_entry)
   - create_journal_entry is ONLY for personal reflections, thoughts, and daily diary entries

AVAILABLE TOOLS AND WHEN TO USE THEM:
Tasks:
  create_task(title, description?, due_date?, priority?)  → create a new task
  list_tasks(status?)                                     → list tasks (status: todo/in_progress/done/all)
  complete_task(task_id)                                  → mark a task as done
  delete_task(task_id)                                    → permanently delete a task

Notes:
  create_note(title, body?, folder_name?)                 → create a note (creates folder if needed)
  list_notes(folder_name?)                                → list notes, optionally filtered by folder
  delete_note(note_id)                                    → permanently delete a note
  create_note_folder(name)                                → create a note folder
  list_note_folders()                                     → list all note folders

Habits:
  create_habit(name, time_of_day?)                        → create a daily habit
  list_habits()                                           → list all habits
  toggle_habit(habit_id)                                  → mark habit complete/incomplete for today
  delete_habit(habit_id)                                  → permanently delete a habit

Goals:
  create_goal(title, description?, target_date?)          → create a long-term goal
  list_goals()                                            → list active goals
  update_goal_progress(goal_id, progress?, status?)       → update progress % or status (active/completed/abandoned)
  delete_goal(goal_id)                                    → permanently delete a goal

Journal (personal reflections only — NOT for food or exercise):
  create_journal_entry(body, mood?, title?)               → create or update today's diary entry
  (mood options: great/good/okay/bad/terrible)

Nutrition (food, meals, calories, macros):
  log_meal(name, calories?, protein_g?, carbs_g?, fat_g?, date?)  → log a food item (call once per item)
  get_nutrition_log(date?)                                          → view what was eaten and totals

Exercise (workouts, physical activity):
  log_exercise(name, duration_min?, sets?, date?)   → log an exercise (sets: [{reps, weight}])
  get_exercise_log(date?)                           → view today's workout

Memory:
  remember_fact(key, value)                               → remember something about the user\
"""

_SYSTEM_PROMPT_TEMPLATE = os.environ.get("ASSISTANT_SYSTEM_PROMPT") or _DEFAULT_SYSTEM_PROMPT


def _system_prompt(memories: dict, master_context: str) -> list[dict]:
    today = date.today()
    memory_text = (
        "\n".join(f"- {k}: {v}" for k, v in memories.items())
        if memories else "Nothing remembered yet."
    )
    context_section = f"\n\nWhat I know about you (big picture):\n{master_context}" if master_context else ""
    text = _SYSTEM_PROMPT_TEMPLATE.format(
        today=today.strftime('%A, %B %d, %Y'),
        memory_text=memory_text,
    ) + context_section
    return [{"text": text}]


def _update_master_context(user_id: str, existing_context: str, facts: dict, user_message: str, reply: str, model_id: str = MODEL_ID) -> None:
    """Summarize what we know about the user and persist it."""
    facts_text = "\n".join(f"- {k}: {v}" for k, v in facts.items()) if facts else "None"
    existing   = f"\n\nExisting summary:\n{existing_context}" if existing_context else ""

    prompt = (
        f"You are updating a personal profile for an AI assistant. "
        f"Based on the information below, write a concise 3-5 sentence paragraph summarizing who this person is: "
        f"their role, interests, goals, habits, preferences, and routines. "
        f"Focus on durable, personal facts. Do not include task IDs, note IDs, or one-off requests."
        f"\n\nKnown facts:\n{facts_text}"
        f"{existing}"
        f"\n\nLatest exchange:\nUser: {user_message[:400]}\nAssistant: {reply[:400]}"
        f"\n\nWrite the updated summary paragraph (plain text, no headings):"
    )
    try:
        resp = _bedrock.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 300},
        )
        context = _clean_reply(resp["output"]["message"]["content"][0]["text"].strip())
        mem.save_master_context(user_id, context)
    except Exception:
        logger.warning("Failed to update master context", exc_info=True)


def chat(user_id: str, user_message: str, model: str | None = None) -> dict:
    model_id = model if model in _ALLOWED_MODELS else MODEL_ID
    try:
        history         = mem.load_history(user_id)
        facts, master   = mem.load_memory(user_id)
        system          = _system_prompt(facts, master)
        messages        = history + [{"role": "user", "content": [{"text": user_message}]}]

        reply        = ""
        link_tags    = []  # [pal-link:...] tags collected from tool results
        total_in     = 0
        total_out    = 0

        for _ in range(MAX_LOOPS):
            resp   = _bedrock.converse(
                modelId=model_id,
                system=system,
                messages=messages,
                toolConfig={"tools": TOOL_SPECS},
                inferenceConfig={"maxTokens": MAX_TOKENS},
            )

            usage = resp.get("usage", {})
            total_in  += usage.get("inputTokens",  0)
            total_out += usage.get("outputTokens", 0)

            output_msg  = resp["output"]["message"]
            stop_reason = resp["stopReason"]
            messages.append(output_msg)

            if stop_reason == "tool_use":
                tool_results = []
                for block in output_msg["content"]:
                    if "toolUse" in block:
                        tu     = block["toolUse"]
                        result = handle_tool(user_id, tu["name"], tu["input"])
                        logger.info("Tool %s → %s", tu["name"], result)
                        # Extract any pal-link tags from the tool result
                        for tag in re.findall(r"\[pal-link:[^\]]+\]", result):
                            link_tags.append(tag)
                        tool_results.append({
                            "toolResult": {
                                "toolUseId": tu["toolUseId"],
                                "content":   [{"text": result}],
                            }
                        })
                messages.append({"role": "user", "content": tool_results})
            else:
                for block in output_msg["content"]:
                    if "text" in block:
                        reply = block["text"]
                        break
                break

        reply = _clean_reply(reply)
        # Append any navigation links collected from tool results
        if link_tags:
            reply = reply.rstrip() + "\n" + " ".join(link_tags)
        mem.save_message(user_id, "user",      user_message)
        mem.save_message(user_id, "assistant", reply)
        mem.update_model_usage(user_id, model_id, total_in, total_out)
        _update_master_context(user_id, master, facts, user_message, reply, model_id)

        return ok({"reply": reply})

    except Exception:
        logger.exception("Error in chat")
        return server_error("Assistant error — please try again")
