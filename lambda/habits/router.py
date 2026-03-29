"""Route dispatch for the habits Lambda."""

from response import error, not_found
import crud


def route(route_key: str, user_id: str, body: dict, path_params: dict) -> dict:
    habit_id = path_params.get("id")

    match route_key:
        case "GET /habits":
            return crud.list_habits(user_id)

        case "POST /habits":
            return crud.create_habit(user_id, body)

        case "PUT /habits/{id}":
            if not habit_id:
                return error("Missing habit id")
            return crud.update_habit(user_id, habit_id, body)

        case "DELETE /habits/{id}":
            if not habit_id:
                return error("Missing habit id")
            return crud.delete_habit(user_id, habit_id)

        case "POST /habits/{id}/toggle":
            if not habit_id:
                return error("Missing habit id")
            return crud.toggle_log(user_id, habit_id, body)

        case _:
            return not_found("Route")
