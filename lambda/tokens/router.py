"""Tokens Lambda router."""

import crud
from response import error, not_found


def route(route_key: str, user_id: str, body: dict, path_params: dict) -> dict:
    id_ = path_params.get("id")

    match route_key:
        case "GET /tokens":
            return crud.list_tokens(user_id)
        case "POST /tokens":
            return crud.create_token(user_id, body)
        case "DELETE /tokens/{id}":
            if not id_:
                return error("Missing token id")
            return crud.delete_token(user_id, id_)
        case _:
            return not_found("Route")
