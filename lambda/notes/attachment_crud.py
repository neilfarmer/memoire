"""File attachment CRUD for the notes Lambda."""

import base64
import boto3
import os
import os.path
import uuid
from urllib.parse import quote

import db
from botocore.exceptions import ClientError
from response import ok, error, no_content, not_found
from utils import now_iso

NOTES_TABLE     = os.environ["NOTES_TABLE"]
FRONTEND_BUCKET = os.environ["FRONTEND_BUCKET"]

_s3 = boto3.client("s3")

# Whitelist of allowed attachment extensions
ALLOWED_EXTENSIONS = {
    ".pdf", ".txt", ".md",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    ".mp3", ".mp4", ".wav",
    ".zip", ".csv",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
}

# Map whitelisted extensions to canonical MIME types
EXTENSION_MIME = {
    ".pdf":  "application/pdf",
    ".txt":  "text/plain",
    ".md":   "text/markdown",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif":  "image/gif",
    ".webp": "image/webp",
    ".svg":  "image/svg+xml",
    ".mp3":  "audio/mpeg",
    ".mp4":  "video/mp4",
    ".wav":  "audio/wav",
    ".zip":  "application/zip",
    ".csv":  "text/csv",
    ".doc":  "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls":  "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt":  "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def _table():
    return db.get_table(NOTES_TABLE)


def create_attachment(user_id: str, note_id: str, body: dict) -> dict:
    note = db.get_item(_table(), user_id, "note_id", note_id)
    if not note:
        return not_found("Note")

    name = (body.get("name") or "").strip()
    try:
        size = int(body.get("size") or 0)
    except (ValueError, TypeError):
        return error("size must be an integer")
    if not name:
        return error("name is required")

    safe_name = "".join(c for c in name if c.isalnum() or c in "._- ")[:200].strip()
    if not safe_name:
        return error("name contains no valid characters")

    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return error(f"File type '{ext or 'unknown'}' is not allowed")

    # Use the canonical MIME type for the extension — ignore the client-declared type
    content_type = EXTENSION_MIME[ext]

    att_id = str(uuid.uuid4())
    key = f"note-attachments/{user_id}/{note_id}/{att_id}/{safe_name}"

    upload_url = _s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": FRONTEND_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=300,
    )

    attachment = {
        "id":         att_id,
        "name":       name,
        "size":       size,
        "type":       content_type,
        "key":        key,
        "created_at": now_iso(),
    }

    _table().update_item(
        Key={"user_id": user_id, "note_id": note_id},
        UpdateExpression="SET #atts = list_append(if_not_exists(#atts, :empty), :new), updated_at = :now",
        ExpressionAttributeNames={"#atts": "attachments"},
        ExpressionAttributeValues={
            ":new":   [attachment],
            ":empty": [],
            ":now":   now_iso(),
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

    try:
        obj = _s3.get_object(Bucket=FRONTEND_BUCKET, Key=target["key"])
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return not_found("Attachment file")
        raise
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
        ExpressionAttributeValues={":atts": updated, ":now": now_iso()},
    )

    return no_content()
