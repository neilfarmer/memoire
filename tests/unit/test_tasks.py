"""Unit tests for lambda/tasks/crud.py and lambda/tasks/folders.py."""

import json
import os

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda, make_table

# ── env vars before module load ───────────────────────────────────────────────
os.environ["TABLE_NAME"] = "test-tasks"
os.environ["FOLDERS_TABLE"] = "test-task-folders"

crud = load_lambda("tasks", "crud.py")
folders = load_lambda("tasks", "folders.py")

TASKS_TABLE = "test-tasks"
FOLDERS_TABLE_NAME = "test-task-folders"


@pytest.fixture
def tbls():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, TASKS_TABLE, "user_id", "task_id")
        make_table(ddb, FOLDERS_TABLE_NAME, "user_id", "folder_id")
        yield


# ── _validate_fields ──────────────────────────────────────────────────────────

class TestValidateFields:
    def test_valid_status(self):
        for s in ("todo", "in_progress", "done"):
            assert crud._validate_fields({"status": s}) is None

    def test_invalid_status(self):
        err = crud._validate_fields({"status": "DONE"})
        assert err is not None
        assert "status" in err

    def test_valid_priority(self):
        for p in ("low", "medium", "high"):
            assert crud._validate_fields({"priority": p}) is None

    def test_invalid_priority(self):
        err = crud._validate_fields({"priority": "urgent"})
        assert err is not None

    def test_notifications_must_be_dict(self):
        err = crud._validate_fields({"notifications": "now"})
        assert err is not None

    def test_valid_before_due(self):
        err = crud._validate_fields({"notifications": {"before_due": ["1h", "1d"]}})
        assert err is None

    def test_invalid_before_due_value(self):
        err = crud._validate_fields({"notifications": {"before_due": ["2h"]}})
        assert err is not None

    def test_valid_recurring(self):
        for v in ("1h", "1d", "1w"):
            assert crud._validate_fields({"notifications": {"recurring": v}}) is None

    def test_invalid_recurring(self):
        err = crud._validate_fields({"notifications": {"recurring": "2w"}})
        assert err is not None

    def test_empty_body_valid(self):
        assert crud._validate_fields({}) is None


# ── list_tasks ────────────────────────────────────────────────────────────────

class TestListTasks:
    def test_empty(self, tbls):
        r = crud.list_tasks(USER)
        assert r["statusCode"] == 200
        assert json.loads(r["body"]) == []

    def test_returns_own_tasks_only(self, tbls):
        crud.create_task(USER, {"title": "Mine"})
        crud.create_task("other", {"title": "Theirs"})
        items = json.loads(crud.list_tasks(USER)["body"])
        assert len(items) == 1
        assert items[0]["title"] == "Mine"


# ── create_task ───────────────────────────────────────────────────────────────

class TestCreateTask:
    def test_requires_title(self, tbls):
        r = crud.create_task(USER, {})
        assert r["statusCode"] == 400

    def test_blank_title_rejected(self, tbls):
        r = crud.create_task(USER, {"title": "   "})
        assert r["statusCode"] == 400

    def test_creates_with_defaults(self, tbls):
        r = crud.create_task(USER, {"title": "Do something"})
        assert r["statusCode"] == 201
        body = json.loads(r["body"])
        assert body["status"] == "todo"
        assert body["priority"] == "medium"
        assert "task_id" in body
        assert "created_at" in body

    def test_creates_with_explicit_fields(self, tbls):
        r = crud.create_task(USER, {
            "title": "Important",
            "status": "in_progress",
            "priority": "high",
            "description": "Details here",
        })
        body = json.loads(r["body"])
        assert body["status"] == "in_progress"
        assert body["priority"] == "high"
        assert body["description"] == "Details here"

    def test_invalid_status_rejected(self, tbls):
        r = crud.create_task(USER, {"title": "Bad", "status": "pending"})
        assert r["statusCode"] == 400

    def test_invalid_priority_rejected(self, tbls):
        r = crud.create_task(USER, {"title": "Bad", "priority": "critical"})
        assert r["statusCode"] == 400

    def test_title_stripped(self, tbls):
        r = crud.create_task(USER, {"title": "  Spaced  "})
        assert json.loads(r["body"])["title"] == "Spaced"

    def test_none_values_not_stored(self, tbls):
        r = crud.create_task(USER, {"title": "No due date"})
        body = json.loads(r["body"])
        assert "due_date" not in body
        assert "notifications" not in body

    def test_title_too_long_rejected(self, tbls):
        r = crud.create_task(USER, {"title": "x" * 501})
        assert r["statusCode"] == 400

    def test_description_too_long_rejected(self, tbls):
        r = crud.create_task(USER, {"title": "OK", "description": "x" * 10_001})
        assert r["statusCode"] == 400


# ── get_task ──────────────────────────────────────────────────────────────────

class TestGetTask:
    def test_returns_task(self, tbls):
        r = crud.create_task(USER, {"title": "Find me"})
        task_id = json.loads(r["body"])["task_id"]
        got = crud.get_task(USER, task_id)
        assert got["statusCode"] == 200
        assert json.loads(got["body"])["title"] == "Find me"

    def test_not_found(self, tbls):
        r = crud.get_task(USER, "does-not-exist")
        assert r["statusCode"] == 404

    def test_cannot_get_other_users_task(self, tbls):
        r = crud.create_task("alice", {"title": "Alice task"})
        task_id = json.loads(r["body"])["task_id"]
        r2 = crud.get_task("bob", task_id)
        assert r2["statusCode"] == 404


# ── update_task ───────────────────────────────────────────────────────────────

class TestUpdateTask:
    def test_updates_fields(self, tbls):
        task_id = json.loads(crud.create_task(USER, {"title": "Old"})["body"])["task_id"]
        r = crud.update_task(USER, task_id, {"title": "New", "status": "done"})
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        assert body["title"] == "New"
        assert body["status"] == "done"

    def test_no_valid_fields_returns_400(self, tbls):
        task_id = json.loads(crud.create_task(USER, {"title": "T"})["body"])["task_id"]
        r = crud.update_task(USER, task_id, {"unknown_field": "x"})
        assert r["statusCode"] == 400

    def test_empty_title_rejected(self, tbls):
        task_id = json.loads(crud.create_task(USER, {"title": "T"})["body"])["task_id"]
        r = crud.update_task(USER, task_id, {"title": ""})
        assert r["statusCode"] == 400

    def test_update_nonexistent_task(self, tbls):
        r = crud.update_task(USER, "ghost-id", {"title": "X"})
        assert r["statusCode"] == 404

    def test_invalid_status_in_update(self, tbls):
        task_id = json.loads(crud.create_task(USER, {"title": "T"})["body"])["task_id"]
        r = crud.update_task(USER, task_id, {"status": "DONE"})
        assert r["statusCode"] == 400

    def test_updating_notifications_resets_sent_tracker(self, tbls):
        task_id = json.loads(crud.create_task(USER, {"title": "T"})["body"])["task_id"]
        r = crud.update_task(USER, task_id, {"notifications": {"before_due": ["1d"]}})
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        assert body.get("notification_sent") == {}


# ── delete_task ───────────────────────────────────────────────────────────────

class TestDeleteTask:
    def test_deletes_task(self, tbls):
        task_id = json.loads(crud.create_task(USER, {"title": "Bye"})["body"])["task_id"]
        r = crud.delete_task(USER, task_id)
        assert r["statusCode"] == 204
        assert crud.get_task(USER, task_id)["statusCode"] == 404

    def test_delete_nonexistent_returns_404(self, tbls):
        r = crud.delete_task(USER, "ghost")
        assert r["statusCode"] == 404


# ── folders: list ─────────────────────────────────────────────────────────────

class TestListFolders:
    def test_creates_inbox_when_empty(self, tbls):
        items = json.loads(folders.list_folders(USER)["body"])
        assert len(items) == 1
        assert items[0]["name"] == "Inbox"

    def test_does_not_duplicate_inbox_on_second_call(self, tbls):
        folders.list_folders(USER)
        items = json.loads(folders.list_folders(USER)["body"])
        assert len(items) == 1

    def test_returns_created_folders(self, tbls):
        folders.create_folder(USER, {"name": "Work"})
        items = json.loads(folders.list_folders(USER)["body"])
        names = {i["name"] for i in items}
        assert "Work" in names


# ── folders: create ───────────────────────────────────────────────────────────

class TestCreateFolder:
    def test_requires_name(self, tbls):
        r = folders.create_folder(USER, {})
        assert r["statusCode"] == 400

    def test_blank_name_rejected(self, tbls):
        r = folders.create_folder(USER, {"name": "   "})
        assert r["statusCode"] == 400

    def test_creates_folder(self, tbls):
        r = folders.create_folder(USER, {"name": "Personal"})
        assert r["statusCode"] == 201
        body = json.loads(r["body"])
        assert body["name"] == "Personal"
        assert "folder_id" in body


# ── folders: update ───────────────────────────────────────────────────────────

class TestUpdateFolder:
    def test_renames_folder(self, tbls):
        folder_id = json.loads(folders.create_folder(USER, {"name": "Old"})["body"])["folder_id"]
        r = folders.update_folder(USER, folder_id, {"name": "New"})
        assert r["statusCode"] == 200
        assert json.loads(r["body"])["name"] == "New"

    def test_nonexistent_folder_returns_404(self, tbls):
        r = folders.update_folder(USER, "ghost", {"name": "x"})
        assert r["statusCode"] == 404

    def test_blank_name_rejected(self, tbls):
        folder_id = json.loads(folders.create_folder(USER, {"name": "X"})["body"])["folder_id"]
        r = folders.update_folder(USER, folder_id, {"name": ""})
        assert r["statusCode"] == 400


# ── folders: delete ───────────────────────────────────────────────────────────

class TestDeleteFolder:
    def test_deletes_folder(self, tbls):
        folder_id = json.loads(folders.create_folder(USER, {"name": "Temp"})["body"])["folder_id"]
        r = folders.delete_folder(USER, folder_id)
        assert r["statusCode"] == 204

    def test_nonexistent_returns_404(self, tbls):
        r = folders.delete_folder(USER, "ghost")
        assert r["statusCode"] == 404

    def test_cascade_deletes_tasks_in_folder(self, tbls):
        folder_id = json.loads(folders.create_folder(USER, {"name": "Proj"})["body"])["folder_id"]
        crud.create_task(USER, {"title": "Task A", "folder_id": folder_id})
        crud.create_task(USER, {"title": "Task B", "folder_id": folder_id})
        crud.create_task(USER, {"title": "Task C"})  # no folder — should survive
        folders.delete_folder(USER, folder_id)
        remaining = json.loads(crud.list_tasks(USER)["body"])
        assert len(remaining) == 1
        assert remaining[0]["title"] == "Task C"
