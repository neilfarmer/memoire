"""Route dispatch for the links Lambda."""

from response import not_found
import crud


def route(route_key: str, user_id: str, body: dict,
          path_params: dict, query_params: dict) -> dict:
    match route_key:
        case "GET /links":
            return crud.list_outbound(user_id, query_params)

        case "GET /backlinks":
            return crud.list_inbound(user_id, query_params)

        case _:
            return not_found("Route")
