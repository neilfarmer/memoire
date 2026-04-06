"""Route dispatch for the favorites Lambda."""

from response import error, not_found
import crud


def route(route_key: str, user_id: str, body: dict, path_params: dict) -> dict:
    favorite_id = path_params.get("id")

    match route_key:
        case "GET /favorites":
            return crud.list_favorites(user_id)

        case "POST /favorites":
            return crud.add_favorite(user_id, body)

        case "DELETE /favorites/{id}":
            if not favorite_id:
                return error("Missing favorite id")
            return crud.remove_favorite(user_id, favorite_id)

        case "PATCH /favorites/{id}":
            if not favorite_id:
                return error("Missing favorite id")
            return crud.update_tags(user_id, favorite_id, body)

        case _:
            return not_found("Route")
