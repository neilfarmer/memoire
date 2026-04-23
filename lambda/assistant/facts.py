"""Canonical fact keys, normalization, smart list handling, and fuzzy dedup.

The assistant stores personal facts as `{memory_key: value}` rows. Values are
either a single string or a comma-separated list. Historically two problems
corrupted this data:

  1. Every value was split on every comma to dedup, which shredded numeric
     and currency facts ("$5,000 emergency fund" -> ["$5", "000 ..."]).
  2. No normalized compare meant "run 5k" and "run a 5k" coexisted as dupes.

This module centralizes the rules so both live extraction and bulk cleanup
use the same logic.
"""

import re

# Canonical keys that the extractor is allowed to use.  Any incoming key is
# routed through ALIASES to one of these.  Unknown keys pass through unchanged
# but the extractor prompt discourages inventing new ones.
CANONICAL_KEYS = {
    "name",
    "occupation",
    "role",
    "pronouns",
    "location",
    "timezone",
    "interests",
    "hobbies",
    "values",
    "personality",
    "communication_style",
    "goal",
    "preference",
    "pet",
    "diet",
    "favorite_food",
    "meal",
    "workout_style",
    "habit",
    "sleep_schedule",
    "family",
    "relationship",
}

ALIASES = {
    # Goal variants -> single "goal" key
    "goals":            "goal",
    "long_term_goal":   "goal",
    "long_term_goals":  "goal",
    "fitness_goal":     "goal",
    "fitness_goals":    "goal",
    "career_goal":      "goal",
    "career_goals":     "goal",
    # Food / diet
    "favorite_foods":   "favorite_food",
    "foods":            "favorite_food",
    "meals":            "meal",
    # Hobbies / interests are kept distinct (one is active, one passive), but
    # collapse plural forms.
    "interest":         "interests",
    "hobby":            "hobbies",
    # Pets
    "pets":             "pet",
    # Preferences
    "preferences":      "preference",
    # Habits
    "habits":           "habit",
    # Relationships / family
    "relationships":    "relationship",
    "spouse":           "family",
    "partner":          "family",
}

# Verbs / phrasing that suggest the item is a one-off task the user mentioned,
# not a durable personal fact.  Used to drop noise from existing data and to
# short-circuit extraction.
_TASK_VERB_RE = re.compile(
    r"^\s*("
    r"go to|pick up|finish|complete|write|build|refactor|deploy|ship|"
    r"send|email|call|review|read chapter|fix|update|debug|"
    r"discover \d+|do the|make the"
    r")\b",
    re.IGNORECASE,
)

# Comma inside a number (e.g. "$5,000") — protect it before splitting on commas.
_NUMBER_COMMA_RE = re.compile(r"(\d),\s*(\d{3})(?!\d)")
_PROTECT_CHAR    = " "

# Short articles and fillers removed before fuzzy compare.
_STOPWORDS = {"a", "an", "the", "to", "of", "in", "on", "at", "for", "my", "your", "i"}


def canonical_key(key: str) -> str:
    """Normalize an incoming key to its canonical form."""
    k = (key or "").strip().lower().replace(" ", "_").replace("-", "_")
    return ALIASES.get(k, k)


def looks_like_task(value: str) -> bool:
    """Heuristic: value looks like an action / task, not a durable fact."""
    v = (value or "").strip()
    if not v:
        return True
    if _TASK_VERB_RE.match(v):
        return True
    # Numeric fragments left behind by the old comma-split bug
    if re.match(r"^\s*\d{3,}\b", v):
        return True
    if re.fullmatch(r"[$£€¥]?\d+(?:[,.]\d+)?", v.strip()):
        return True
    return False


def normalize_for_compare(value: str) -> str:
    """Return a lowercase, article/punct-stripped form used ONLY for dedup."""
    v = (value or "").lower()
    v = re.sub(r"[^\w\s]", " ", v)         # punctuation -> space
    v = re.sub(r"\s+", " ", v).strip()
    tokens = [t for t in v.split(" ") if t and t not in _STOPWORDS]
    return " ".join(tokens)


def _protect_numbers(value: str) -> str:
    """Replace commas inside numbers with a placeholder so split won't eat them."""
    return _NUMBER_COMMA_RE.sub(lambda m: m.group(1) + _PROTECT_CHAR + m.group(2), value)


def split_items(value: str) -> list[str]:
    """Split value into items iff it really looks like a list; else return [value]."""
    if not value:
        return []
    protected = _protect_numbers(value)
    parts     = [p.strip() for p in protected.split(",") if p.strip()]
    if len(parts) < 2:
        return [value.strip()]
    return parts


def is_list_value(value: str) -> bool:
    """True when the stored value should be treated as a list of items."""
    return len(split_items(value)) > 1


def dedup_items(items: list[str]) -> list[str]:
    """Stable fuzzy-dedup: preserves first occurrence, drops near-dupes."""
    seen_norms: set[str] = set()
    out: list[str] = []
    for item in items:
        norm = normalize_for_compare(item)
        if not norm:
            continue
        # Also drop items that are a substring of (or superset of) something
        # already kept — "run 5k" vs "run a 5k in under 25 minutes".
        if any(norm == s or norm in s or s in norm for s in seen_norms):
            continue
        seen_norms.add(norm)
        out.append(item.strip())
    return out


def merge_values(existing: str, incoming: str) -> str:
    """Merge an incoming value into an existing stored value, with fuzzy dedup.

    Handles the common case where the old bug left broken currency fragments
    in `existing` — those get dropped by the looks_like_task check.
    """
    items = split_items(existing) + split_items(incoming)
    items = [i for i in items if not looks_like_task(i)]
    items = dedup_items(items)
    return ", ".join(items)


def clean_value(value: str) -> str:
    """Clean a single stored value in place: split -> drop tasks -> dedup."""
    items = split_items(value)
    items = [i for i in items if not looks_like_task(i)]
    items = dedup_items(items)
    return ", ".join(items)


def cleanup_facts(facts: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Canonicalize keys, merge aliases, fuzzy-dedup values, drop task noise.

    Returns (new_facts, removed_keys) where removed_keys is the list of
    original keys that no longer exist (either aliased to a canonical key or
    entirely empty after cleanup).
    """
    canonical: dict[str, list[str]] = {}
    seen_original: set[str] = set()

    for raw_key, raw_value in facts.items():
        seen_original.add(raw_key)
        key = canonical_key(raw_key)
        if not key or key.startswith("__"):
            continue
        for item in split_items(raw_value):
            if looks_like_task(item):
                continue
            canonical.setdefault(key, []).append(item)

    new_facts: dict[str, str] = {}
    for key, items in canonical.items():
        deduped = dedup_items(items)
        if deduped:
            new_facts[key] = ", ".join(deduped)

    removed = [k for k in seen_original if k not in new_facts]
    return new_facts, removed
