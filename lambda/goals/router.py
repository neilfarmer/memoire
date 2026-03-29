"""Route dispatch for the goals Lambda."""

from response import error, not_found
import crud


def route(route_key: str, user_id: str, body: dict, path_params: dict) -> dict:
    goal_id = path_params.get("id")

    match route_key:
        case "GET /goals":
            return crud.list_goals(user_id)

        case "POST /goals":
            return crud.create_goal(user_id, body)

        case "GET /goals/{id}":
            if not goal_id:
                return error("Missing goal id")
            return crud.get_goal(user_id, goal_id)

        case "PUT /goals/{id}":
            if not goal_id:
                return error("Missing goal id")
            return crud.update_goal(user_id, goal_id, body)

        case "DELETE /goals/{id}":
            if not goal_id:
                return error("Missing goal id")
            return crud.delete_goal(user_id, goal_id)

        case _:
            return not_found("Route")
