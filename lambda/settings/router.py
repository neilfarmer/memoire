"""Route dispatch for the settings Lambda."""

from response import not_found
import crud


def route(route_key: str, user_id: str, body: dict) -> dict:
    match route_key:
        case "GET /settings":
            return crud.get_settings(user_id)

        case "PUT /settings":
            return crud.update_settings(user_id, body)

        case "POST /settings/test-notification":
            return crud.test_notification(user_id, body)

        case _:
            return not_found("Route")
