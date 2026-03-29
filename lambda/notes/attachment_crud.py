"""File attachment CRUD for the notes Lambda."""

import base64
import boto3
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import db
from response import ok, error, no_content, not_found

NOTES_TABLE     = os.environ["NOTES_TABLE"]
FRONTEND_BUCKET = os.environ["FRONTEND_BUCKET"]

_s3 = boto3.client("s3")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table():
    return db.get_table(NOTES_TABLE)


def create_attachment(user_id: str, note_id: str, body: dict) -> dict:
    note = db.get_item(_table(), user_id, "note_id", note_id)
    if not note:
        return not_found("Note")

    name = (body.get("name") or "").strip()
    size = int(body.get("size") or 0)
    file_type = body.get("type") or "application/octet-stream"

    if not name:
        return error("name is required")

    att_id    = str(uuid.uuid4())
    safe_name = "".join(c for c in name if c.isalnum() or c in "._- ")[:200].strip()
    if not safe_name:
        safe_name = att_id
    key = f"note-attachments/{user_id}/{note_id}/{att_id}/{safe_name}"

    upload_url = _s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": FRONTEND_BUCKET, "Key": key, "ContentType": file_type},
        ExpiresIn=300,
    )

    attachment = {
        "id":         att_id,
        "name":       name,
        "size":       size,
        "type":       file_type,
        "key":        key,
        "created_at": _now(),
    }

    _table().update_item(
        Key={"user_id": user_id, "note_id": note_id},
        UpdateExpression="SET #atts = list_append(if_not_exists(#atts, :empty), :new), updated_at = :now",
        ExpressionAttributeNames={"#atts": "attachments"},
        ExpressionAttributeValues={
            ":new":   [attachment],
            ":empty": [],
            ":now":   _now(),
        },
    )

    return ok({"upload_url": upload_url, "attachment": attachment})


def download_attachment(user_id: str, note_id: str, att_id: str) -> dict:
    note = db.get_item(_table(), user_id, "note_id", note_id)
    if not note:
        return not_found("Note")

    attachments = note.get("attachments") or []
    target = next((a for a in attachments if a["id"] == att_id), None)
    if not target:
        return not_found("Attachment")

    obj = _s3.get_object(Bucket=FRONTEND_BUCKET, Key=target["key"])
    content = obj["Body"].read()
    content_type = target.get("type", "application/octet-stream")
    filename_encoded = quote(target["name"])

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": content_type,
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename_encoded}",
        },
        "body": base64.b64encode(content).decode(),
        "isBase64Encoded": True,
    }


def delete_attachment(user_id: str, note_id: str, att_id: str) -> dict:
    note = db.get_item(_table(), user_id, "note_id", note_id)
    if not note:
        return not_found("Note")

    attachments = note.get("attachments") or []
    target = next((a for a in attachments if a["id"] == att_id), None)
    if not target:
        return not_found("Attachment")

    try:
        _s3.delete_object(Bucket=FRONTEND_BUCKET, Key=target["key"])
    except Exception:
        pass  # best-effort S3 delete

    updated = [a for a in attachments if a["id"] != att_id]
    _table().update_item(
        Key={"user_id": user_id, "note_id": note_id},
        UpdateExpression="SET #atts = :atts, updated_at = :now",
        ExpressionAttributeNames={"#atts": "attachments"},
        ExpressionAttributeValues={":atts": updated, ":now": _now()},
    )

    return no_content()
