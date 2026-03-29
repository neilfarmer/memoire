"""Image upload and download for the notes Lambda."""

import base64
import boto3
import os
import uuid

from response import ok, error, not_found

FRONTEND_BUCKET = os.environ["FRONTEND_BUCKET"]

_s3 = boto3.client("s3")

ALLOWED_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
EXT_MAP = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp"}


def generate_upload_url(user_id: str, body: dict) -> dict:
    content_type = body.get("content_type", "")
    if content_type not in ALLOWED_TYPES:
        return error(f"Unsupported image type: {content_type}")

    ext = EXT_MAP[content_type]
    key = f"note-images/{user_id}/{uuid.uuid4()}.{ext}"

    upload_url = _s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": FRONTEND_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=300,
    )
    # Return the key path, not a public URL — frontend embeds this in markdown
    # and resolves it via the authenticated GET /notes/images endpoint at render time.
    return ok({"upload_url": upload_url, "image_url": key})


def download_image(user_id: str, key: str) -> dict:
    # Validate the key belongs to this user: note-images/{user_id}/...
    parts = key.split("/")
    if len(parts) < 3 or parts[0] != "note-images" or parts[1] != user_id:
        return {"statusCode": 403, "headers": {"Content-Type": "application/json"},
                "body": '{"error":"Forbidden"}', "isBase64Encoded": False}

    try:
        obj = _s3.get_object(Bucket=FRONTEND_BUCKET, Key=key)
        content = obj["Body"].read()
        content_type = obj.get("ContentType", "image/png")
        return {
            "statusCode": 200,
            "headers": {"Content-Type": content_type},
            "body": base64.b64encode(content).decode(),
            "isBase64Encoded": True,
        }
    except Exception:
        return not_found("Image")
