"""Route dispatch for the bookmarks Lambda."""

from response import error, not_found
import crud


def route(route_key: str, user_id: str, body: dict,
          path_params: dict, query_params: dict) -> dict:
    id_ = path_params.get("id")

    match route_key:
        case "GET /bookmarks":
            return crud.list_bookmarks(user_id, query_params)

        case "POST /bookmarks":
            return crud.create_bookmark(user_id, body)

        case "GET /bookmarks/{id}":
            if not id_:
                return error("Missing bookmark id")
            return crud.get_bookmark(user_id, id_)

        case "PUT /bookmarks/{id}":
            if not id_:
                return error("Missing bookmark id")
            return crud.update_bookmark(user_id, id_, body)

        case "DELETE /bookmarks/{id}":
            if not id_:
                return error("Missing bookmark id")
            return crud.delete_bookmark(user_id, id_)

        case _:
            return not_found("Route")
