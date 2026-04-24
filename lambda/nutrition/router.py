"""Route dispatch for the nutrition Lambda."""

from response import error, not_found
import crud


def route(route_key: str, user_id: str, body: dict, path_params: dict, query_params: dict) -> dict:
    log_date = path_params.get("date")

    if route_key == "GET /nutrition":
        return crud.list_logs(user_id)

    if route_key == "GET /nutrition/summary":
        return crud.summary(user_id, query_params)

    if route_key == "GET /nutrition/meals/recent":
        return crud.recent_meals(user_id, query_params)

    if route_key == "GET /nutrition/{date}":
        if not log_date:
            return error("date required")
        return crud.get_log(user_id, log_date)

    if route_key == "PUT /nutrition/{date}":
        if not log_date:
            return error("date required")
        return crud.upsert_log(user_id, log_date, body)

    if route_key == "DELETE /nutrition/{date}":
        if not log_date:
            return error("date required")
        return crud.delete_log(user_id, log_date)

    return not_found("Route")
