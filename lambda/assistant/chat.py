"""Main Bedrock chat logic for the AI assistant."""

import json
import logging
import os
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


def _system_prompt(memories: dict) -> list[dict]:
    today = date.today()
    memory_text = (
        "\n".join(f"- {k}: {v}" for k, v in memories.items())
        if memories else "Nothing remembered yet."
    )
    return [{
        "text": f"""You are a warm, helpful personal assistant for Memoire, a personal productivity app.
You help the user manage their tasks, notes, habits, goals, and journal entries.
Today is {today.strftime('%A, %B %d, %Y')}.

What you know about the user:
{memory_text}

Guidelines:
- Be concise and friendly.
- When the user asks to create something, call the appropriate tool immediately — don't ask for confirmation.
- After taking action, confirm briefly in 1-2 sentences.
- If you learn something meaningful about the user (preferences, routines, goals), call remember_fact.
- When listing items, keep it brief."""
    }]


def chat(user_id: str, user_message: str) -> dict:
    try:
        history   = mem.load_history(user_id)
        memories  = mem.load_memory(user_id)
        system    = _system_prompt(memories)
        messages  = history + [{"role": "user", "content": [{"text": user_message}]}]

        reply = ""

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

        mem.save_message(user_id, "user",      user_message)
        mem.save_message(user_id, "assistant", reply)

        return ok({"reply": reply})

    except Exception:
        logger.exception("Error in chat")
        return server_error("Assistant error — please try again")
