"""Unit tests for lambda/diagrams/crud.py and router.py."""

import json
import os

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda, make_table

# ── env vars before module load ───────────────────────────────────────────────
os.environ["DIAGRAMS_TABLE"] = "test-diagrams"

crud   = load_lambda("diagrams", "crud.py")
router = load_lambda("diagrams", "router.py")

DIAGRAMS_TABLE = "test-diagrams"


@pytest.fixture
def tbl():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, DIAGRAMS_TABLE, "user_id", "diagram_id")
        yield ddb


# ══════════════════════════════════════════════════════════════════════════════
# List
# ══════════════════════════════════════════════════════════════════════════════

class TestListDiagrams:
    def test_empty_for_new_user(self, tbl):
        result = crud.list_diagrams(USER)
        assert result["statusCode"] == 200
        assert json.loads(result["body"]) == []

    def test_returns_created_diagrams(self, tbl):
        crud.create_diagram(USER, {"title": "My Diagram"})
        result = crud.list_diagrams(USER)
        items = json.loads(result["body"])
        assert len(items) == 1
        assert items[0]["title"] == "My Diagram"

    def test_list_excludes_elements(self, tbl):
        crud.create_diagram(USER, {"title": "D", "elements": [{"type": "rectangle"}]})
        result = crud.list_diagrams(USER)
        item = json.loads(result["body"])[0]
        assert "elements" not in item

    def test_sorted_by_updated_at_desc(self, tbl):
        crud.create_diagram(USER, {"title": "First"})
        crud.create_diagram(USER, {"title": "Second"})
        items = json.loads(crud.list_diagrams(USER)["body"])
        # Most recently created should appear first
        assert items[0]["title"] == "Second"


# ══════════════════════════════════════════════════════════════════════════════
# Create
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateDiagram:
    def test_creates_with_title(self, tbl):
        result = crud.create_diagram(USER, {"title": "Arch diagram"})
        assert result["statusCode"] == 201
        body = json.loads(result["body"])
        assert body["title"] == "Arch diagram"
        assert "diagram_id" in body
        assert "created_at" in body
        assert "updated_at" in body

    def test_defaults_to_untitled(self, tbl):
        result = crud.create_diagram(USER, {})
        assert result["statusCode"] == 201
        assert json.loads(result["body"])["title"] == "Untitled"

    def test_stores_elements(self, tbl):
        elements = [{"type": "rectangle", "id": "abc"}]
        result = crud.create_diagram(USER, {"title": "T", "elements": elements})
        body = json.loads(result["body"])
        assert body["elements"] == elements

    def test_stores_app_state(self, tbl):
        app_state = {"viewBackgroundColor": "#ffffff"}
        result = crud.create_diagram(USER, {"title": "T", "app_state": app_state})
        body = json.loads(result["body"])
        assert body["app_state"] == app_state

    def test_title_truncated_at_200_chars(self, tbl):
        long_title = "x" * 300
        result = crud.create_diagram(USER, {"title": long_title})
        body = json.loads(result["body"])
        assert len(body["title"]) == 200


# ══════════════════════════════════════════════════════════════════════════════
# Update
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateDiagram:
    def test_updates_title(self, tbl):
        created = json.loads(crud.create_diagram(USER, {"title": "Old"})["body"])
        diagram_id = created["diagram_id"]
        result = crud.update_diagram(USER, diagram_id, {"title": "New"})
        assert result["statusCode"] == 200
        assert json.loads(result["body"])["title"] == "New"

    def test_updates_elements(self, tbl):
        created = json.loads(crud.create_diagram(USER, {"title": "T"})["body"])
        diagram_id = created["diagram_id"]
        new_elements = [{"type": "ellipse", "id": "x1"}]
        result = crud.update_diagram(USER, diagram_id, {"elements": new_elements})
        assert json.loads(result["body"])["elements"] == new_elements

    def test_not_found_returns_404(self, tbl):
        result = crud.update_diagram(USER, "nonexistent", {"title": "X"})
        assert result["statusCode"] == 404

    def test_preserves_fields_not_in_body(self, tbl):
        elements = [{"type": "text"}]
        created = json.loads(
            crud.create_diagram(USER, {"title": "Keep", "elements": elements})["body"]
        )
        diagram_id = created["diagram_id"]
        # Only update title
        result = crud.update_diagram(USER, diagram_id, {"title": "New Title"})
        body = json.loads(result["body"])
        assert body["elements"] == elements
        assert body["title"] == "New Title"


# ══════════════════════════════════════════════════════════════════════════════
# Delete
# ══════════════════════════════════════════════════════════════════════════════

class TestDeleteDiagram:
    def test_deletes_existing(self, tbl):
        created = json.loads(crud.create_diagram(USER, {"title": "To delete"})["body"])
        result = crud.delete_diagram(USER, created["diagram_id"])
        assert result["statusCode"] == 204
        assert json.loads(crud.list_diagrams(USER)["body"]) == []

    def test_not_found_returns_404(self, tbl):
        result = crud.delete_diagram(USER, "nonexistent")
        assert result["statusCode"] == 404


# ══════════════════════════════════════════════════════════════════════════════
# Get single
# ══════════════════════════════════════════════════════════════════════════════

class TestGetDiagram:
    def test_returns_full_diagram(self, tbl):
        elements = [{"type": "rectangle"}]
        created = json.loads(
            crud.create_diagram(USER, {"title": "Full", "elements": elements})["body"]
        )
        result = crud.get_diagram(USER, created["diagram_id"])
        body = json.loads(result["body"])
        assert body["title"] == "Full"
        assert body["elements"] == elements

    def test_not_found_returns_404(self, tbl):
        result = crud.get_diagram(USER, "missing")
        assert result["statusCode"] == 404


# ══════════════════════════════════════════════════════════════════════════════
# Router
# ══════════════════════════════════════════════════════════════════════════════

class TestRouter:
    def test_get_diagrams(self, tbl):
        result = router.route("GET /diagrams", USER, {}, {})
        assert result["statusCode"] == 200

    def test_post_diagrams(self, tbl):
        result = router.route("POST /diagrams", USER, {"title": "R"}, {})
        assert result["statusCode"] == 201

    def test_get_diagram_by_id(self, tbl):
        created = json.loads(router.route("POST /diagrams", USER, {"title": "G"}, {})["body"])
        result = router.route("GET /diagrams/{id}", USER, {}, {"id": created["diagram_id"]})
        assert result["statusCode"] == 200
        assert json.loads(result["body"])["title"] == "G"

    def test_get_diagram_missing_id(self, tbl):
        result = router.route("GET /diagrams/{id}", USER, {}, {})
        assert result["statusCode"] == 400

    def test_put_diagrams_missing_id(self, tbl):
        result = router.route("PUT /diagrams/{id}", USER, {}, {})
        assert result["statusCode"] == 400

    def test_delete_diagrams_missing_id(self, tbl):
        result = router.route("DELETE /diagrams/{id}", USER, {}, {})
        assert result["statusCode"] == 400

    def test_put_diagrams_with_id(self, tbl):
        created = json.loads(router.route("POST /diagrams", USER, {"title": "T"}, {})["body"])
        result = router.route("PUT /diagrams/{id}", USER, {"title": "U"}, {"id": created["diagram_id"]})
        assert result["statusCode"] == 200

    def test_delete_diagrams_with_id(self, tbl):
        created = json.loads(router.route("POST /diagrams", USER, {"title": "T"}, {})["body"])
        result = router.route("DELETE /diagrams/{id}", USER, {}, {"id": created["diagram_id"]})
        assert result["statusCode"] == 204

    def test_unknown_route(self, tbl):
        result = router.route("PATCH /diagrams", USER, {}, {})
        assert result["statusCode"] == 404
