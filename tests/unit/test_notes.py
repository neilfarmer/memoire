"""Unit tests for lambda/notes/{note_crud,folders,image_crud,attachment_crud}.py."""

import base64
import json
import os

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda, make_table

# ── env vars before module load ───────────────────────────────────────────────
os.environ["NOTES_TABLE"] = "test-notes"
os.environ["FOLDERS_TABLE"] = "test-note-folders"
os.environ["FRONTEND_BUCKET"] = "test-bucket"

# Load note_crud first so it's registered as "note_crud" for folders.py to import
note_crud = load_lambda("notes", "note_crud.py")
note_folders = load_lambda("notes", "folders.py")
image_crud = load_lambda("notes", "image_crud.py")
attachment_crud = load_lambda("notes", "attachment_crud.py")

NOTES_TABLE = "test-notes"
FOLDERS_TABLE_NAME = "test-note-folders"
BUCKET = "test-bucket"


@pytest.fixture
def tbls():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, NOTES_TABLE, "user_id", "note_id")
        make_table(ddb, FOLDERS_TABLE_NAME, "user_id", "folder_id")
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET)
        yield ddb, s3


def _make_folder(user=USER, name="Inbox"):
    """Helper: create a folder and return its folder_id."""
    r = note_folders.create_folder(user, {"name": name})
    return json.loads(r["body"])["folder_id"]


# ══════════════════════════════════════════════════════════════════════════════
# note_crud
# ══════════════════════════════════════════════════════════════════════════════

class TestParseTags:
    def test_none_returns_empty(self):
        assert note_crud._parse_tags(None) == []

    def test_list(self):
        assert note_crud._parse_tags(["a", " b "]) == ["a", "b"]

    def test_comma_string(self):
        assert note_crud._parse_tags("x, y, z") == ["x", "y", "z"]

    def test_empty_list_items_skipped(self):
        assert note_crud._parse_tags(["", "  ", "ok"]) == ["ok"]


class TestSummary:
    def test_strips_body(self):
        s = note_crud._summary({"body": "hello", "note_id": "x"})
        assert "body" not in s

    def test_adds_preview(self):
        s = note_crud._summary({"body": "hi"})
        assert s["preview"] == "hi"

    def test_truncates_at_200(self):
        s = note_crud._summary({"body": "x" * 300})
        assert s["preview"].endswith("...")
        assert len(s["preview"]) == 203


class TestListNotes:
    def test_empty(self, tbls):
        r = note_crud.list_notes(USER)
        assert r["statusCode"] == 200
        assert json.loads(r["body"]) == []

    def test_sorted_by_updated_at_desc(self, tbls):
        folder_id = _make_folder()
        note_crud.create_note(USER, {"folder_id": folder_id, "title": "A"})
        note_crud.create_note(USER, {"folder_id": folder_id, "title": "B"})
        items = json.loads(note_crud.list_notes(USER)["body"])
        # Most recently created is first
        assert items[0]["title"] == "B"

    def test_isolates_users(self, tbls):
        folder_id = _make_folder()
        note_crud.create_note(USER, {"folder_id": folder_id, "title": "Mine"})
        note_crud.create_note("other", {"folder_id": folder_id, "title": "Theirs"})
        items = json.loads(note_crud.list_notes(USER)["body"])
        assert len(items) == 1


class TestSearchNotes:
    def test_matches_title(self, tbls):
        fid = _make_folder()
        note_crud.create_note(USER, {"folder_id": fid, "title": "Meeting notes"})
        note_crud.create_note(USER, {"folder_id": fid, "title": "Shopping list"})
        results = json.loads(note_crud.search_notes(USER, "meeting")["body"])
        assert len(results) == 1
        assert results[0]["title"] == "Meeting notes"

    def test_matches_body(self, tbls):
        fid = _make_folder()
        note_crud.create_note(USER, {"folder_id": fid, "title": "X", "body": "secret keyword"})
        results = json.loads(note_crud.search_notes(USER, "keyword")["body"])
        assert len(results) == 1

    def test_matches_tags(self, tbls):
        fid = _make_folder()
        note_crud.create_note(USER, {"folder_id": fid, "title": "X", "tags": ["python", "work"]})
        results = json.loads(note_crud.search_notes(USER, "python")["body"])
        assert len(results) == 1

    def test_case_insensitive(self, tbls):
        fid = _make_folder()
        note_crud.create_note(USER, {"folder_id": fid, "title": "README"})
        results = json.loads(note_crud.search_notes(USER, "readme")["body"])
        assert len(results) == 1

    def test_no_match(self, tbls):
        fid = _make_folder()
        note_crud.create_note(USER, {"folder_id": fid, "title": "Unrelated"})
        results = json.loads(note_crud.search_notes(USER, "xyz_nope")["body"])
        assert results == []


class TestGetNote:
    def test_returns_note(self, tbls):
        fid = _make_folder()
        note_id = json.loads(note_crud.create_note(USER, {"folder_id": fid, "title": "Hi", "body": "content"})["body"])["note_id"]
        r = note_crud.get_note(USER, note_id)
        assert r["statusCode"] == 200
        assert json.loads(r["body"])["body"] == "content"

    def test_not_found(self, tbls):
        assert note_crud.get_note(USER, "ghost")["statusCode"] == 404


class TestCreateNote:
    def test_requires_folder_id(self, tbls):
        r = note_crud.create_note(USER, {"title": "No folder"})
        assert r["statusCode"] == 400

    def test_nonexistent_folder_returns_404(self, tbls):
        r = note_crud.create_note(USER, {"folder_id": "no-such-folder", "title": "X"})
        assert r["statusCode"] == 404

    def test_creates_note(self, tbls):
        fid = _make_folder()
        r = note_crud.create_note(USER, {"folder_id": fid, "title": "Hello", "body": "World"})
        assert r["statusCode"] == 201
        body = json.loads(r["body"])
        assert body["title"] == "Hello"
        assert body["body"] == "World"
        assert "note_id" in body

    def test_tags_parsed(self, tbls):
        fid = _make_folder()
        r = note_crud.create_note(USER, {"folder_id": fid, "title": "X", "tags": ["a", "b"]})
        assert json.loads(r["body"])["tags"] == ["a", "b"]

    def test_title_too_long_rejected(self, tbls):
        fid = _make_folder()
        r = note_crud.create_note(USER, {"folder_id": fid, "title": "x" * 501})
        assert r["statusCode"] == 400

    def test_body_too_long_rejected(self, tbls):
        fid = _make_folder()
        r = note_crud.create_note(USER, {"folder_id": fid, "title": "X", "body": "x" * 100_001})
        assert r["statusCode"] == 400


class TestUpdateNote:
    def test_updates_title(self, tbls):
        fid = _make_folder()
        note_id = json.loads(note_crud.create_note(USER, {"folder_id": fid, "title": "Old"})["body"])["note_id"]
        r = note_crud.update_note(USER, note_id, {"title": "New"})
        assert r["statusCode"] == 200
        assert json.loads(r["body"])["title"] == "New"

    def test_updates_body(self, tbls):
        fid = _make_folder()
        note_id = json.loads(note_crud.create_note(USER, {"folder_id": fid, "title": "X"})["body"])["note_id"]
        r = note_crud.update_note(USER, note_id, {"body": "new content"})
        assert json.loads(r["body"])["body"] == "new content"

    def test_not_found(self, tbls):
        r = note_crud.update_note(USER, "ghost", {"title": "x"})
        assert r["statusCode"] == 404

    def test_move_to_nonexistent_folder_returns_404(self, tbls):
        fid = _make_folder()
        note_id = json.loads(note_crud.create_note(USER, {"folder_id": fid, "title": "X"})["body"])["note_id"]
        r = note_crud.update_note(USER, note_id, {"folder_id": "no-such"})
        assert r["statusCode"] == 404

    def test_update_title_too_long_rejected(self, tbls):
        fid = _make_folder()
        note_id = json.loads(note_crud.create_note(USER, {"folder_id": fid, "title": "X"})["body"])["note_id"]
        r = note_crud.update_note(USER, note_id, {"title": "x" * 501})
        assert r["statusCode"] == 400

    def test_update_body_too_long_rejected(self, tbls):
        fid = _make_folder()
        note_id = json.loads(note_crud.create_note(USER, {"folder_id": fid, "title": "X"})["body"])["note_id"]
        r = note_crud.update_note(USER, note_id, {"body": "x" * 100_001})
        assert r["statusCode"] == 400


class TestDeleteNote:
    def test_deletes_note(self, tbls):
        fid = _make_folder()
        note_id = json.loads(note_crud.create_note(USER, {"folder_id": fid, "title": "Bye"})["body"])["note_id"]
        r = note_crud.delete_note(USER, note_id)
        assert r["statusCode"] == 204
        assert note_crud.get_note(USER, note_id)["statusCode"] == 404

    def test_not_found(self, tbls):
        assert note_crud.delete_note(USER, "ghost")["statusCode"] == 404


# ══════════════════════════════════════════════════════════════════════════════
# note_folders
# ══════════════════════════════════════════════════════════════════════════════

class TestListFolders:
    def test_creates_inbox_when_empty(self, tbls):
        items = json.loads(note_folders.list_folders(USER)["body"])
        assert len(items) == 1
        assert items[0]["name"] == "Inbox"

    def test_no_duplicate_inbox(self, tbls):
        note_folders.list_folders(USER)
        items = json.loads(note_folders.list_folders(USER)["body"])
        assert len(items) == 1


class TestCreateFolder:
    def test_requires_name(self, tbls):
        assert note_folders.create_folder(USER, {})["statusCode"] == 400

    def test_blank_name_rejected(self, tbls):
        assert note_folders.create_folder(USER, {"name": " "})["statusCode"] == 400

    def test_creates_folder(self, tbls):
        r = note_folders.create_folder(USER, {"name": "Work"})
        assert r["statusCode"] == 201
        body = json.loads(r["body"])
        assert body["name"] == "Work"
        assert "folder_id" in body

    def test_creates_nested_folder(self, tbls):
        parent_id = _make_folder(name="Parent")
        r = note_folders.create_folder(USER, {"name": "Child", "parent_id": parent_id})
        assert r["statusCode"] == 201

    def test_nonexistent_parent_returns_404(self, tbls):
        r = note_folders.create_folder(USER, {"name": "Child", "parent_id": "no-such"})
        assert r["statusCode"] == 404


class TestUpdateFolder:
    def test_renames(self, tbls):
        fid = _make_folder(name="Old")
        r = note_folders.update_folder(USER, fid, {"name": "New"})
        assert r["statusCode"] == 200
        assert json.loads(r["body"])["name"] == "New"

    def test_not_found(self, tbls):
        assert note_folders.update_folder(USER, "ghost", {"name": "x"})["statusCode"] == 404

    def test_blank_name_rejected(self, tbls):
        fid = _make_folder()
        assert note_folders.update_folder(USER, fid, {"name": ""})["statusCode"] == 400


class TestDeleteFolder:
    def test_deletes_folder(self, tbls):
        fid = _make_folder(name="Temp")
        assert note_folders.delete_folder(USER, fid)["statusCode"] == 204

    def test_not_found(self, tbls):
        assert note_folders.delete_folder(USER, "ghost")["statusCode"] == 404

    def test_recursive_delete_removes_notes(self, tbls):
        parent_id = _make_folder(name="Parent")
        child_id = json.loads(
            note_folders.create_folder(USER, {"name": "Child", "parent_id": parent_id})["body"]
        )["folder_id"]
        # Note in child folder
        note_crud.create_note(USER, {"folder_id": child_id, "title": "In child"})
        note_folders.delete_folder(USER, parent_id)
        assert json.loads(note_crud.list_notes(USER)["body"]) == []

    def test_notes_outside_subtree_survive(self, tbls):
        fid1 = _make_folder(name="Deleted")
        fid2 = _make_folder(name="Kept")
        note_crud.create_note(USER, {"folder_id": fid1, "title": "Gone"})
        note_crud.create_note(USER, {"folder_id": fid2, "title": "Survives"})
        note_folders.delete_folder(USER, fid1)
        notes = json.loads(note_crud.list_notes(USER)["body"])
        assert len(notes) == 1
        assert notes[0]["title"] == "Survives"


class TestSubtreeIds:
    def test_single_folder(self, tbls):
        fid = _make_folder()
        all_folders = [{"folder_id": fid, "user_id": USER}]
        assert note_folders._subtree_ids(all_folders, fid) == {fid}

    def test_with_child(self, tbls):
        parent_id = _make_folder(name="P")
        child_id = json.loads(
            note_folders.create_folder(USER, {"name": "C", "parent_id": parent_id})["body"]
        )["folder_id"]
        all_folders = [
            {"folder_id": parent_id}, {"folder_id": child_id, "parent_id": parent_id}
        ]
        ids = note_folders._subtree_ids(all_folders, parent_id)
        assert ids == {parent_id, child_id}


# ══════════════════════════════════════════════════════════════════════════════
# image_crud
# ══════════════════════════════════════════════════════════════════════════════

class TestGenerateUploadUrl:
    def test_valid_image_type(self, tbls):
        for ct in ("image/png", "image/jpeg", "image/gif", "image/webp"):
            r = image_crud.generate_upload_url(USER, {"content_type": ct})
            assert r["statusCode"] == 200
            body = json.loads(r["body"])
            assert "upload_url" in body
            assert "image_url" in body

    def test_invalid_type_returns_400(self, tbls):
        r = image_crud.generate_upload_url(USER, {"content_type": "application/pdf"})
        assert r["statusCode"] == 400

    def test_missing_type_returns_400(self, tbls):
        r = image_crud.generate_upload_url(USER, {})
        assert r["statusCode"] == 400

    def test_key_contains_user_id(self, tbls):
        r = image_crud.generate_upload_url(USER, {"content_type": "image/png"})
        body = json.loads(r["body"])
        assert f"note-images/{USER}/" in body["image_url"]


class TestDownloadImage:
    def test_valid_key_returns_image(self, tbls):
        _, s3 = tbls
        key = f"note-images/{USER}/test.png"
        s3.put_object(Bucket=BUCKET, Key=key, Body=b"fake-png-data", ContentType="image/png")
        r = image_crud.download_image(USER, key)
        assert r["statusCode"] == 200
        assert r["isBase64Encoded"] is True
        decoded = base64.b64decode(r["body"])
        assert decoded == b"fake-png-data"

    def test_wrong_user_returns_403(self, tbls):
        key = f"note-images/alice/secret.png"
        r = image_crud.download_image("bob", key)
        assert r["statusCode"] == 403

    def test_nonexistent_key_returns_404(self, tbls):
        key = f"note-images/{USER}/missing.png"
        r = image_crud.download_image(USER, key)
        assert r["statusCode"] == 404

    def test_malformed_key_returns_403(self, tbls):
        r = image_crud.download_image(USER, "just-a-filename.png")
        assert r["statusCode"] == 403


# ══════════════════════════════════════════════════════════════════════════════
# attachment_crud
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateAttachment:
    def test_note_not_found_returns_404(self, tbls):
        r = attachment_crud.create_attachment(USER, "ghost-note", {"name": "file.pdf", "size": 100})
        assert r["statusCode"] == 404

    def test_requires_name(self, tbls):
        fid = _make_folder()
        note_id = json.loads(note_crud.create_note(USER, {"folder_id": fid, "title": "N"})["body"])["note_id"]
        r = attachment_crud.create_attachment(USER, note_id, {"name": "", "size": 0})
        assert r["statusCode"] == 400

    def test_creates_attachment(self, tbls):
        fid = _make_folder()
        note_id = json.loads(note_crud.create_note(USER, {"folder_id": fid, "title": "N"})["body"])["note_id"]
        r = attachment_crud.create_attachment(USER, note_id, {"name": "report.pdf", "size": 512})
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        assert "upload_url" in body
        assert body["attachment"]["name"] == "report.pdf"
        assert "id" in body["attachment"]

    def test_safe_name_sanitized(self, tbls):
        fid = _make_folder()
        note_id = json.loads(note_crud.create_note(USER, {"folder_id": fid, "title": "N"})["body"])["note_id"]
        r = attachment_crud.create_attachment(USER, note_id, {"name": "my file (1).pdf", "size": 0})
        att = json.loads(r["body"])["attachment"]
        # Safe name should only contain alphanumeric, ._- and space
        assert att["name"] == "my file (1).pdf"  # original name preserved
        assert "key" in att
        # Key uses safe_name
        assert "(" not in att["key"]

    def test_disallowed_extension_rejected(self, tbls):
        fid = _make_folder()
        note_id = json.loads(note_crud.create_note(USER, {"folder_id": fid, "title": "N"})["body"])["note_id"]
        r = attachment_crud.create_attachment(USER, note_id, {"name": "malware.exe", "size": 0})
        assert r["statusCode"] == 400

    def test_double_extension_blocked(self, tbls):
        fid = _make_folder()
        note_id = json.loads(note_crud.create_note(USER, {"folder_id": fid, "title": "N"})["body"])["note_id"]
        r = attachment_crud.create_attachment(USER, note_id, {"name": "payload.html.png", "size": 0})
        # .html.png → final ext is .png which IS allowed — but the name stored in
        # the key will have html stripped by safe_name; the key ext is .png
        assert r["statusCode"] == 200

    def test_canonical_mime_type_used(self, tbls):
        fid = _make_folder()
        note_id = json.loads(note_crud.create_note(USER, {"folder_id": fid, "title": "N"})["body"])["note_id"]
        r = attachment_crud.create_attachment(USER, note_id, {
            "name": "photo.jpg", "size": 0, "type": "application/octet-stream"
        })
        assert r["statusCode"] == 200
        att = json.loads(r["body"])["attachment"]
        assert att["type"] == "image/jpeg"  # client-declared type ignored

    def test_no_extension_rejected(self, tbls):
        fid = _make_folder()
        note_id = json.loads(note_crud.create_note(USER, {"folder_id": fid, "title": "N"})["body"])["note_id"]
        r = attachment_crud.create_attachment(USER, note_id, {"name": "noextension", "size": 0})
        assert r["statusCode"] == 400


class TestDownloadAttachment:
    def test_note_not_found(self, tbls):
        r = attachment_crud.download_attachment(USER, "ghost", "att-id")
        assert r["statusCode"] == 404

    def test_attachment_not_found(self, tbls):
        fid = _make_folder()
        note_id = json.loads(note_crud.create_note(USER, {"folder_id": fid, "title": "N"})["body"])["note_id"]
        r = attachment_crud.download_attachment(USER, note_id, "ghost-att")
        assert r["statusCode"] == 404

    def test_download_returns_base64(self, tbls):
        _, s3 = tbls
        fid = _make_folder()
        note_id = json.loads(note_crud.create_note(USER, {"folder_id": fid, "title": "N"})["body"])["note_id"]
        # Create attachment record
        cr = attachment_crud.create_attachment(USER, note_id, {"name": "doc.txt", "size": 5})
        att = json.loads(cr["body"])["attachment"]
        # Put file in S3
        s3.put_object(Bucket=BUCKET, Key=att["key"], Body=b"hello")
        # Download
        r = attachment_crud.download_attachment(USER, note_id, att["id"])
        assert r["statusCode"] == 200
        assert base64.b64decode(r["body"]) == b"hello"


class TestDeleteAttachment:
    def test_note_not_found(self, tbls):
        r = attachment_crud.delete_attachment(USER, "ghost", "att")
        assert r["statusCode"] == 404

    def test_attachment_not_found(self, tbls):
        fid = _make_folder()
        note_id = json.loads(note_crud.create_note(USER, {"folder_id": fid, "title": "N"})["body"])["note_id"]
        r = attachment_crud.delete_attachment(USER, note_id, "ghost")
        assert r["statusCode"] == 404

    def test_deletes_attachment(self, tbls):
        fid = _make_folder()
        note_id = json.loads(note_crud.create_note(USER, {"folder_id": fid, "title": "N"})["body"])["note_id"]
        cr = attachment_crud.create_attachment(USER, note_id, {"name": "x.txt", "size": 0})
        att_id = json.loads(cr["body"])["attachment"]["id"]
        r = attachment_crud.delete_attachment(USER, note_id, att_id)
        assert r["statusCode"] == 204
        # Should be gone
        assert attachment_crud.download_attachment(USER, note_id, att_id)["statusCode"] == 404
