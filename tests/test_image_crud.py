#!/usr/bin/env python3
"""
Unit tests for lambda/notes/image_crud.py — focused on path traversal
prevention in download_image().

No deployment or AWS credentials required.

Usage:
    python -m pytest tests/test_image_crud.py -v
    make test-unit
"""

import importlib.util
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# ── Load module with mocked boto3 ─────────────────────────────────────────────

os.environ.setdefault("FRONTEND_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

_mock_boto3 = MagicMock()

# response helpers are imported from the layer; provide minimal stubs
_mock_response = MagicMock()
_mock_response.ok.side_effect       = lambda body: {"statusCode": 200, "body": body}
_mock_response.not_found.side_effect = lambda _: {"statusCode": 404}

with patch.dict(sys.modules, {"boto3": _mock_boto3, "response": _mock_response}):
    _spec = importlib.util.spec_from_file_location(
        "image_crud",
        os.path.join(os.path.dirname(__file__), "..", "lambda", "notes", "image_crud.py"),
    )
    image_crud = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(image_crud)


# ── Helpers ───────────────────────────────────────────────────────────────────

USER_ID = "user-abc-123"

def _forbidden(result):
    return result.get("statusCode") == 403


def _ok(result):
    return result.get("statusCode") == 200


def _mock_s3_get(content=b"imgdata", content_type="image/png"):
    mock_obj = {"Body": MagicMock(read=MagicMock(return_value=content)), "ContentType": content_type}
    image_crud._s3.get_object = MagicMock(return_value=mock_obj)


# ── Path traversal tests ──────────────────────────────────────────────────────

class TestDownloadImagePathTraversal(unittest.TestCase):

    def test_valid_key_allowed(self):
        _mock_s3_get()
        key = f"note-images/{USER_ID}/abc123.png"
        self.assertTrue(_ok(image_crud.download_image(USER_ID, key)))

    def test_traversal_to_other_user_blocked(self):
        key = f"note-images/{USER_ID}/../../other-user/secret.png"
        self.assertTrue(_forbidden(image_crud.download_image(USER_ID, key)))

    def test_traversal_escaping_prefix_entirely_blocked(self):
        key = f"note-images/{USER_ID}/../../../etc/passwd"
        self.assertTrue(_forbidden(image_crud.download_image(USER_ID, key)))

    def test_double_traversal_blocked(self):
        key = f"note-images/{USER_ID}/subdir/../../{USER_ID}/../../other/file.png"
        self.assertTrue(_forbidden(image_crud.download_image(USER_ID, key)))

    def test_wrong_user_prefix_blocked(self):
        key = f"note-images/other-user/image.png"
        self.assertTrue(_forbidden(image_crud.download_image(USER_ID, key)))

    def test_wrong_top_prefix_blocked(self):
        key = f"note-attachments/{USER_ID}/image.png"
        self.assertTrue(_forbidden(image_crud.download_image(USER_ID, key)))

    def test_too_few_parts_blocked(self):
        key = f"note-images/{USER_ID}"
        self.assertTrue(_forbidden(image_crud.download_image(USER_ID, key)))

    def test_normalized_key_used_for_s3_call(self):
        """After normalization a clean path should still reach S3."""
        _mock_s3_get()
        key = f"note-images/{USER_ID}/subdir/image.png"
        image_crud.download_image(USER_ID, key)
        image_crud._s3.get_object.assert_called_once_with(
            Bucket="test-bucket", Key=key
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
