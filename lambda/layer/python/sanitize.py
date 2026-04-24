"""Escape user-controlled content injected into LLM prompts.

Prompts are assembled by concatenating developer instructions with user
content (task titles, memory facts, tool results). Without isolation, a
user can embed text that looks like instructions and steer the model.
We fence each untrusted section with typed XML tags and neutralize any
occurrence of those tags in the payload so user input cannot close the
fence.
"""

import re

# Tags that, if they appear inside user content, could be mistaken by the
# model for developer-defined structural markers. Any untrusted string
# going into a prompt should be passed through ``neutralize`` against at
# least its own fence tag; passing the full set is a safe default.
STRUCTURAL_TAGS = (
    "user_input",
    "tool_result",
    "activity",
    "facts",
    "existing_facts",
    "profile",
    "reply",
    "memory",
    "system",
    "response",
    "thinking",
)


def neutralize(text, tags=STRUCTURAL_TAGS):
    """Replace `<tag>` / `</tag>` occurrences with bracket-escaped forms.

    Case-insensitive and whitespace-tolerant so ``< / User_Input >`` is
    also caught. Returns an empty string for ``None``.
    """
    if text is None:
        return ""
    out = str(text)
    for tag in tags:
        out = re.sub(
            rf"<\s*(/?)\s*{re.escape(tag)}\s*>",
            lambda m, t=tag: f"[{m.group(1)}{t}]",
            out,
            flags=re.IGNORECASE,
        )
    return out


def fence(tag, text):
    """Wrap text in `<tag>...</tag>`, escaping any internal copies of the tag."""
    payload = neutralize(text, (tag,))
    return f"<{tag}>\n{payload}\n</{tag}>"
