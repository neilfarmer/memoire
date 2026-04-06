"""Route dispatch for the feeds Lambda."""

from response import error, not_found
import crud


def route(route_key: str, user_id: str, body: dict, path_params: dict) -> dict:
    feed_id = path_params.get("id")

    match route_key:
        case "GET /feeds":
            return crud.list_feeds(user_id)

        case "POST /feeds":
            return crud.add_feed(user_id, body)

        case "DELETE /feeds/{id}":
            if not feed_id:
                return error("Missing feed id")
            return crud.delete_feed(user_id, feed_id)

        case "GET /feeds/articles":
            return crud.get_articles(user_id)

        case "GET /feeds/article-text":
            url = path_params.get("url") or body.get("url") or ""
            return crud.fetch_article_text(user_id, url)

        case _:
            return not_found("Route")
