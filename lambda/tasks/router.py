"""Route dispatch for the tasks Lambda."""

from response import error, not_found
import crud


def route(route_key: str, user_id: str, body: dict, path_params: dict) -> dict:
    task_id = path_params.get("id")

    match route_key:
        case "GET /tasks":
            return crud.list_tasks(user_id)

        case "POST /tasks":
            return crud.create_task(user_id, body)

        case "GET /tasks/{id}":
            if not task_id:
                return error("Missing task id")
            return crud.get_task(user_id, task_id)

        case "PUT /tasks/{id}":
            if not task_id:
                return error("Missing task id")
            return crud.update_task(user_id, task_id, body)

        case "DELETE /tasks/{id}":
            if not task_id:
                return error("Missing task id")
            return crud.delete_task(user_id, task_id)

        case _:
            return not_found("Route")
