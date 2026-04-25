"""Read endpoints for the links graph.

Writers (notes, journal, tasks) keep the table in sync via
`links_util.sync_links` in the shared layer. This module only exposes
read-only views for the backlinks panel and the assistant tool.
"""

from response import ok, error
from links_util import LINK_TYPES, query_inbound, query_outbound


def _validate(query_params: dict, src_or_tgt: str) -> tuple[str, str] | dict:
    t = (query_params.get(f"{src_or_tgt}_type") or "").strip().lower()
    i = (query_params.get(f"{src_or_tgt}_id")   or "").strip()
    if not t:
        return error(f"{src_or_tgt}_type is required")
    if t not in LINK_TYPES:
        return error(f"{src_or_tgt}_type must be one of: {', '.join(sorted(LINK_TYPES))}")
    if not i:
        return error(f"{src_or_tgt}_id is required")
    return (t, i)


def list_outbound(user_id: str, query_params: dict) -> dict:
    parsed = _validate(query_params, "source")
    if isinstance(parsed, dict):
        return parsed
    source_type, source_id = parsed
    items = query_outbound(user_id, source_type, source_id)
    items.sort(key=lambda i: i.get("created_at", ""))
    return ok(items)


def list_inbound(user_id: str, query_params: dict) -> dict:
    parsed = _validate(query_params, "target")
    if isinstance(parsed, dict):
        return parsed
    target_type, target_id = parsed
    items = query_inbound(user_id, target_type, target_id)
    items.sort(key=lambda i: i.get("created_at", ""))
    return ok(items)
