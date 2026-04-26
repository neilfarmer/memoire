"""Route dispatch for the tasks Lambda."""

from response import error, not_found
import crud
import folders as f
import auto_schedule as auto


def route(route_key: str, user_id: str, body: dict,
          path_params: dict, query_params: dict) -> dict:
    id_ = path_params.get("id")

    match route_key:
        # ── Folders ───────────────────────────────────────────────────────────
        case "GET /tasks/folders":
            return f.list_folders(user_id)

        case "POST /tasks/folders":
            return f.create_folder(user_id, body)

        case "PUT /tasks/folders/{id}":
            if not id_:
                return error("Missing folder id")
            return f.update_folder(user_id, id_, body)

        case "DELETE /tasks/folders/{id}":
            if not id_:
                return error("Missing folder id")
            return f.delete_folder(user_id, id_)

        # ── Tasks ─────────────────────────────────────────────────────────────
        case "GET /tasks":
            return crud.list_tasks(user_id)

        case "GET /tasks/calendar":
            return crud.list_calendar(user_id, query_params)

        case "POST /tasks/auto-schedule":
            return auto.auto_schedule(user_id, body)

        case "POST /tasks":
            return crud.create_task(user_id, body)

        case "GET /tasks/{id}":
            if not id_:
                return error("Missing task id")
            return crud.get_task(user_id, id_)

        case "PUT /tasks/{id}":
            if not id_:
                return error("Missing task id")
            return crud.update_task(user_id, id_, body)

        case "DELETE /tasks/{id}":
            if not id_:
                return error("Missing task id")
            return crud.delete_task(user_id, id_)

        case _:
            return not_found("Route")
