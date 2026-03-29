"""Route dispatch for the journal Lambda."""

from response import error, not_found
import crud


def route(route_key: str, user_id: str, body: dict,
          path_params: dict, query_params: dict) -> dict:
    entry_date = path_params.get("date")

    match route_key:
        case "GET /journal":
            q = query_params.get("q", "").strip()
            return crud.search_entries(user_id, q) if q else crud.list_entries(user_id)

        case "GET /journal/{date}":
            if not entry_date:
                return error("Missing date")
            return crud.get_entry(user_id, entry_date)

        case "PUT /journal/{date}":
            if not entry_date:
                return error("Missing date")
            return crud.upsert_entry(user_id, entry_date, body)

        case "DELETE /journal/{date}":
            if not entry_date:
                return error("Missing date")
            return crud.delete_entry(user_id, entry_date)

        case _:
            return not_found("Route")
