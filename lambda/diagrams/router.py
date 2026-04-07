"""Route dispatch for the diagrams Lambda."""

from response import error, not_found
import crud


def route(route_key: str, user_id: str, body: dict, path_params: dict) -> dict:
    diagram_id = path_params.get("id")

    match route_key:
        case "GET /diagrams":
            return crud.list_diagrams(user_id)

        case "POST /diagrams":
            return crud.create_diagram(user_id, body)

        case "GET /diagrams/{id}":
            if not diagram_id:
                return error("Missing diagram id")
            return crud.get_diagram(user_id, diagram_id)

        case "PUT /diagrams/{id}":
            if not diagram_id:
                return error("Missing diagram id")
            return crud.update_diagram(user_id, diagram_id, body)

        case "DELETE /diagrams/{id}":
            if not diagram_id:
                return error("Missing diagram id")
            return crud.delete_diagram(user_id, diagram_id)

        case _:
            return not_found("Route")
