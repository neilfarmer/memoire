"""Route dispatch for the Fitbit Lambda."""

from response import not_found
import crud
import oauth


def route(route_key: str, user_id: str, body: dict, path_params: dict, query_params: dict) -> dict:
    if route_key == "GET /fitbit/today":
        return crud.get_today(user_id)

    if route_key == "GET /fitbit/status":
        return crud.get_status(user_id)

    if route_key == "GET /fitbit/auth/start":
        return oauth.start(user_id, query_params)

    if route_key == "POST /fitbit/auth/callback":
        return oauth.callback(user_id, body)

    if route_key == "POST /fitbit/disconnect":
        return crud.disconnect(user_id)

    if route_key == "POST /fitbit/sync":
        return crud.sync_now(user_id)

    return not_found("Route")
