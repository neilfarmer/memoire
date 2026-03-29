"""Route dispatch for the notes Lambda."""

from response import error, not_found
import folders as f
import note_crud as n
import image_crud as img
import attachment_crud as att


def route(route_key: str, user_id: str, body: dict,
          path_params: dict, query_params: dict) -> dict:
    folder_id = path_params.get("id")
    note_id   = path_params.get("id")

    match route_key:
        # ── Folders ──────────────────────────────────────────────────────────
        case "GET /notes/folders":
            return f.list_folders(user_id)

        case "POST /notes/folders":
            return f.create_folder(user_id, body)

        case "PUT /notes/folders/{id}":
            if not folder_id:
                return error("Missing folder id")
            return f.update_folder(user_id, folder_id, body)

        case "DELETE /notes/folders/{id}":
            if not folder_id:
                return error("Missing folder id")
            return f.delete_folder(user_id, folder_id)

        # ── Images ───────────────────────────────────────────────────────────
        case "POST /notes/images":
            return img.generate_upload_url(user_id, body)

        case "GET /notes/images":
            key = query_params.get("key", "")
            return img.download_image(user_id, key)

        # ── Attachments ───────────────────────────────────────────────────────
        case "POST /notes/{id}/attachments":
            if not note_id:
                return error("Missing note id")
            return att.create_attachment(user_id, note_id, body)

        case "GET /notes/{id}/attachments/{att_id}":
            att_id = path_params.get("att_id")
            if not note_id or not att_id:
                return error("Missing id")
            return att.download_attachment(user_id, note_id, att_id)

        case "DELETE /notes/{id}/attachments/{att_id}":
            att_id = path_params.get("att_id")
            if not note_id or not att_id:
                return error("Missing id")
            return att.delete_attachment(user_id, note_id, att_id)

        # ── Notes ─────────────────────────────────────────────────────────────
        case "GET /notes":
            q = query_params.get("q", "").strip()
            return n.search_notes(user_id, q) if q else n.list_notes(user_id)

        case "GET /notes/{id}":
            if not note_id:
                return error("Missing note id")
            return n.get_note(user_id, note_id)

        case "POST /notes":
            return n.create_note(user_id, body)

        case "PUT /notes/{id}":
            if not note_id:
                return error("Missing note id")
            return n.update_note(user_id, note_id, body)

        case "DELETE /notes/{id}":
            if not note_id:
                return error("Missing note id")
            return n.delete_note(user_id, note_id)

        case _:
            return not_found("Route")
