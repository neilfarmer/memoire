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

MODEL_ID   = os.environ.get("ASSISTANT_MODEL_ID", "amazon.nova-lite-v1:0")
MAX_TOKENS = 1024
MAX_LOOPS  = 6

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
1. ALWAYS call the appropriate tool before confirming any action. NEVER claim to have created, updated, or listed anything without first invoking the tool. The tools are the only way actions actually happen — if you don't call a tool, nothing is saved and nothing is shown to the user.
2. To create a task → call create_task. To create a note → call create_note. To create a habit → call create_habit. To create a goal → call create_goal. To write a journal entry → call create_journal_entry. To list items → call the appropriate list_* tool.
3. Do NOT narrate what you are about to do. Just call the tool immediately.
4. After the tool returns a result, confirm briefly in 1–2 sentences.
5. If you learn something meaningful about the user (preferences, routines, goals), call remember_fact.
6. Be concise and friendly. When listing items, keep it brief.\
"""

_SYSTEM_PROMPT_TEMPLATE = os.environ.get("ASSISTANT_SYSTEM_PROMPT") or _DEFAULT_SYSTEM_PROMPT


def _system_prompt(memories: dict) -> list[dict]:
    today = date.today()
    memory_text = (
        "\n".join(f"- {k}: {v}" for k, v in memories.items())
        if memories else "Nothing remembered yet."
    )
    text = _SYSTEM_PROMPT_TEMPLATE.format(
        today=today.strftime('%A, %B %d, %Y'),
        memory_text=memory_text,
    )
    return [{"text": text}]


def chat(user_id: str, user_message: str) -> dict:
    try:
        history   = mem.load_history(user_id)
        memories  = mem.load_memory(user_id)
        system    = _system_prompt(memories)
        messages  = history + [{"role": "user", "content": [{"text": user_message}]}]

        reply      = ""
        link_tags  = []  # [pal-link:...] tags collected from tool results

        for _ in range(MAX_LOOPS):
            resp   = _bedrock.converse(
                modelId=MODEL_ID,
                system=system,
                messages=messages,
                toolConfig={"tools": TOOL_SPECS},
                inferenceConfig={"maxTokens": MAX_TOKENS},
            )

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

        return ok({"reply": reply})

    except Exception:
        logger.exception("Error in chat")
        return server_error("Assistant error — please try again")
