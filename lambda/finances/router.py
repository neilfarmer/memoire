"""Route dispatch for the finances Lambda."""

from response import error, not_found
import crud


def route(route_key: str, user_id: str, body: dict,
          path_params: dict, query_params: dict) -> dict:
    id_ = path_params.get("id")

    match route_key:
        # ── Debts ─────────────────────────────────────────────────────────────
        case "GET /debts":
            return crud.list_debts(user_id)

        case "POST /debts":
            return crud.create_debt(user_id, body)

        case "PUT /debts/{id}":
            if not id_:
                return error("Missing debt id")
            return crud.update_debt(user_id, id_, body)

        case "DELETE /debts/{id}":
            if not id_:
                return error("Missing debt id")
            return crud.delete_debt(user_id, id_)

        # ── Income ────────────────────────────────────────────────────────────
        case "GET /income":
            return crud.list_income(user_id)

        case "POST /income":
            return crud.create_income(user_id, body)

        case "PUT /income/{id}":
            if not id_:
                return error("Missing income id")
            return crud.update_income(user_id, id_, body)

        case "DELETE /income/{id}":
            if not id_:
                return error("Missing income id")
            return crud.delete_income(user_id, id_)

        # ── Fixed expenses ────────────────────────────────────────────────────
        case "GET /fixed-expenses":
            return crud.list_expenses(user_id)

        case "POST /fixed-expenses":
            return crud.create_expense(user_id, body)

        case "PUT /fixed-expenses/{id}":
            if not id_:
                return error("Missing expense id")
            return crud.update_expense(user_id, id_, body)

        case "DELETE /fixed-expenses/{id}":
            if not id_:
                return error("Missing expense id")
            return crud.delete_expense(user_id, id_)

        # ── Summary ───────────────────────────────────────────────────────────
        case "GET /finances/summary":
            return crud.get_summary(user_id)

        case _:
            return not_found("Route")
