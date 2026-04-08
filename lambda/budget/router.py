"""Route dispatch for the budget Lambda."""

from response import error, not_found
import crud


def route(route_key: str, user_id: str, body: dict,
          path_params: dict, query_params: dict) -> dict:
    id_ = path_params.get("id")

    match route_key:
        # ── Transactions ──────────────────────────────────────────────────────
        case "GET /transactions":
            return crud.list_transactions(user_id, query_params)

        case "POST /transactions":
            return crud.create_transaction(user_id, body)

        case "GET /transactions/{id}":
            if not id_:
                return error("Missing transaction id")
            return crud.get_transaction(user_id, id_)

        case "PUT /transactions/{id}":
            if not id_:
                return error("Missing transaction id")
            return crud.update_transaction(user_id, id_, body)

        case "DELETE /transactions/{id}":
            if not id_:
                return error("Missing transaction id")
            return crud.delete_transaction(user_id, id_)

        # ── Budgets ───────────────────────────────────────────────────────────
        case "GET /budgets":
            return crud.list_budgets(user_id, query_params)

        case "POST /budgets":
            return crud.create_budget(user_id, body)

        case "PUT /budgets/{id}":
            if not id_:
                return error("Missing budget id")
            return crud.update_budget(user_id, id_, body)

        case "DELETE /budgets/{id}":
            if not id_:
                return error("Missing budget id")
            return crud.delete_budget(user_id, id_)

        # ── Summary ───────────────────────────────────────────────────────────
        case "GET /summary":
            return crud.get_summary(user_id, query_params)

        case _:
            return not_found("Route")
