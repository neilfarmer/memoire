"""Route dispatch for the health Lambda."""

from response import error, not_found
import crud


def route(route_key: str, user_id: str, body: dict, path_params: dict, query_params: dict) -> dict:
    log_date = path_params.get("date")

    if route_key == "GET /health":
        return crud.list_logs(user_id)

    if route_key == "GET /health/summary":
        return crud.summary(user_id, query_params)

    if route_key == "GET /health/exercises/recent":
        return crud.recent_exercises(user_id, query_params)

    if route_key == "GET /health/{date}":
        if not log_date:
            return error("date required")
        return crud.get_log(user_id, log_date)

    if route_key == "PUT /health/{date}":
        if not log_date:
            return error("date required")
        return crud.upsert_log(user_id, log_date, body)

    if route_key == "DELETE /health/{date}":
        if not log_date:
            return error("date required")
        return crud.delete_log(user_id, log_date)

    return not_found("Route")
