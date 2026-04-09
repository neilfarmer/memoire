"""Unit tests for lambda/bookmarks/crud.py and router.py."""

import json
import os
from unittest.mock import patch, MagicMock

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda, make_table

# ── env vars before module load ───────────────────────────────────────────────
os.environ["TABLE_NAME"] = "test-bookmarks"

crud   = load_lambda("bookmarks", "crud.py")
router = load_lambda("bookmarks", "router.py")

TABLE_NAME = "test-bookmarks"

SAMPLE_HTML = b"""<!DOCTYPE html>
<html>
<head>
  <title>Example Page</title>
  <meta name="description" content="A great example page.">
  <link rel="icon" href="/favicon.ico">
</head>
<body>Hello</body>
</html>"""


def _mock_urlopen(body: bytes = SAMPLE_HTML, final_url: str = "https://example.com/"):
    resp = MagicMock()
    resp.read.return_value = body
    resp.geturl.return_value = final_url
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


@pytest.fixture
def tbl():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, TABLE_NAME, "user_id", "bookmark_id")
        yield ddb


# ══════════════════════════════════════════════════════════════════════════════
# Metadata scraping
# ══════════════════════════════════════════════════════════════════════════════

class TestScrapeMetadata:
    def test_extracts_title(self):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen()):
            meta = crud._scrape_metadata("https://example.com/")
        assert meta["title"] == "Example Page"

    def test_extracts_description(self):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen()):
            meta = crud._scrape_metadata("https://example.com/")
        assert meta["description"] == "A great example page."

    def test_extracts_favicon_from_link_tag(self):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen()):
            meta = crud._scrape_metadata("https://example.com/")
        assert meta["favicon_url"] == "https://example.com/favicon.ico"

    def test_fallback_favicon_on_no_link_tag(self):
        html = b"<html><head><title>X</title></head></html>"
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(html)):
            meta = crud._scrape_metadata("https://example.com/page")
        assert meta["favicon_url"] == "https://example.com/favicon.ico"

    def test_returns_empty_on_network_error(self):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            meta = crud._scrape_metadata("https://example.com/")
        assert meta == {"title": "", "description": "", "favicon_url": ""}

    def test_og_description_preferred(self):
        html = b"""<html><head>
          <meta property="og:description" content="OG desc">
          <meta name="description" content="Plain desc">
        </head></html>"""
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(html)):
            meta = crud._scrape_metadata("https://example.com/")
        assert meta["description"] == "OG desc"


# ══════════════════════════════════════════════════════════════════════════════
# Tag validation
# ══════════════════════════════════════════════════════════════════════════════

class TestValidateTags:
    def test_none_returns_empty_list(self):
        tags, err = crud._validate_tags(None)
        assert err is None
        assert tags == []

    def test_valid_list(self):
        tags, err = crud._validate_tags(["python", "tools"])
        assert err is None
        assert tags == ["python", "tools"]

    def test_deduplication(self):
        tags, err = crud._validate_tags(["a", "b", "a"])
        assert err is None
        assert tags == ["a", "b"]

    def test_empty_strings_stripped(self):
        tags, err = crud._validate_tags(["", "  ", "real"])
        assert err is None
        assert tags == ["real"]

    def test_not_a_list_returns_error(self):
        _, err = crud._validate_tags("python")
        assert err is not None

    def test_too_many_tags(self):
        _, err = crud._validate_tags([str(i) for i in range(crud.MAX_TAGS + 1)])
        assert err is not None

    def test_tag_too_long(self):
        _, err = crud._validate_tags(["x" * (crud.MAX_TAG_LEN + 1)])
        assert err is not None


# ══════════════════════════════════════════════════════════════════════════════
# CRUD operations
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateBookmark:
    def test_creates_with_scraped_metadata(self, tbl):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen()):
            resp = crud.create_bookmark(USER, {"url": "https://example.com/"})
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert body["title"] == "Example Page"
        assert body["description"] == "A great example page."
        assert body["bookmark_id"]
        assert body["archived"] is False
        assert body["favourited"] is False

    def test_caller_title_overrides_scraped(self, tbl):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen()):
            resp = crud.create_bookmark(USER, {"url": "https://example.com/", "title": "My Title"})
        body = json.loads(resp["body"])
        assert body["title"] == "My Title"

    def test_requires_url(self, tbl):
        resp = crud.create_bookmark(USER, {})
        assert resp["statusCode"] == 400

    def test_rejects_non_http_url(self, tbl):
        resp = crud.create_bookmark(USER, {"url": "ftp://example.com/"})
        assert resp["statusCode"] == 400

    def test_stores_tags(self, tbl):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen()):
            resp = crud.create_bookmark(USER, {"url": "https://example.com/", "tags": ["python", "tools"]})
        body = json.loads(resp["body"])
        assert body["tags"] == ["python", "tools"]

    def test_invalid_tags_rejected(self, tbl):
        resp = crud.create_bookmark(USER, {"url": "https://example.com/", "tags": "not-a-list"})
        assert resp["statusCode"] == 400


class TestListBookmarks:
    def _create(self, tbl, url="https://example.com/", tags=None, archived=False):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen()):
            body = {"url": url, "tags": tags or []}
            resp = crud.create_bookmark(USER, body)
        if archived:
            item_id = json.loads(resp["body"])["bookmark_id"]
            crud.update_bookmark(USER, item_id, {"archived": True})
        return json.loads(resp["body"])

    def test_list_returns_active(self, tbl):
        self._create(tbl)
        resp = crud.list_bookmarks(USER, {})
        assert resp["statusCode"] == 200
        items = json.loads(resp["body"])
        assert len(items) == 1

    def test_archived_hidden_by_default(self, tbl):
        self._create(tbl, archived=True)
        resp = crud.list_bookmarks(USER, {})
        items = json.loads(resp["body"])
        assert items == []

    def test_archived_filter_shows_archived(self, tbl):
        self._create(tbl, archived=True)
        resp = crud.list_bookmarks(USER, {"archived": "true"})
        items = json.loads(resp["body"])
        assert len(items) == 1

    def test_tag_filter(self, tbl):
        self._create(tbl, url="https://a.com/", tags=["python"])
        self._create(tbl, url="https://b.com/", tags=["js"])
        resp = crud.list_bookmarks(USER, {"tag": "python"})
        items = json.loads(resp["body"])
        assert len(items) == 1
        assert items[0]["tags"] == ["python"]

    def test_search_filter(self, tbl):
        self._create(tbl, url="https://example.com/")
        resp = crud.list_bookmarks(USER, {"q": "example"})
        items = json.loads(resp["body"])
        assert len(items) == 1

    def test_search_no_match(self, tbl):
        self._create(tbl)
        resp = crud.list_bookmarks(USER, {"q": "zzznomatch"})
        items = json.loads(resp["body"])
        assert items == []


class TestGetBookmark:
    def test_get_existing(self, tbl):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen()):
            created = json.loads(crud.create_bookmark(USER, {"url": "https://example.com/"})["body"])
        resp = crud.get_bookmark(USER, created["bookmark_id"])
        assert resp["statusCode"] == 200
        assert json.loads(resp["body"])["bookmark_id"] == created["bookmark_id"]

    def test_get_missing_returns_404(self, tbl):
        resp = crud.get_bookmark(USER, "nonexistent-id")
        assert resp["statusCode"] == 404


class TestUpdateBookmark:
    def test_update_note(self, tbl):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen()):
            created = json.loads(crud.create_bookmark(USER, {"url": "https://example.com/"})["body"])
        resp = crud.update_bookmark(USER, created["bookmark_id"], {"note": "My note"})
        assert resp["statusCode"] == 200
        assert json.loads(resp["body"])["note"] == "My note"

    def test_archive_toggle(self, tbl):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen()):
            created = json.loads(crud.create_bookmark(USER, {"url": "https://example.com/"})["body"])
        resp = crud.update_bookmark(USER, created["bookmark_id"], {"archived": True})
        assert json.loads(resp["body"])["archived"] is True

    def test_favourite_toggle(self, tbl):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen()):
            created = json.loads(crud.create_bookmark(USER, {"url": "https://example.com/"})["body"])
        resp = crud.update_bookmark(USER, created["bookmark_id"], {"favourited": True})
        assert json.loads(resp["body"])["favourited"] is True

    def test_update_missing_returns_404(self, tbl):
        resp = crud.update_bookmark(USER, "nonexistent-id", {"note": "x"})
        assert resp["statusCode"] == 404

    def test_url_change_triggers_rescrape(self, tbl):
        new_html = b"<html><head><title>New Page</title></head></html>"
        with patch("urllib.request.urlopen", return_value=_mock_urlopen()):
            created = json.loads(crud.create_bookmark(USER, {"url": "https://example.com/"})["body"])
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(new_html, "https://new.com/")):
            resp = crud.update_bookmark(USER, created["bookmark_id"], {"url": "https://new.com/"})
        assert json.loads(resp["body"])["title"] == "New Page"

    def test_no_fields_returns_error(self, tbl):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen()):
            created = json.loads(crud.create_bookmark(USER, {"url": "https://example.com/"})["body"])
        resp = crud.update_bookmark(USER, created["bookmark_id"], {})
        assert resp["statusCode"] == 400


class TestDeleteBookmark:
    def test_delete_existing(self, tbl):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen()):
            created = json.loads(crud.create_bookmark(USER, {"url": "https://example.com/"})["body"])
        resp = crud.delete_bookmark(USER, created["bookmark_id"])
        assert resp["statusCode"] == 204
        assert crud.get_bookmark(USER, created["bookmark_id"])["statusCode"] == 404

    def test_delete_missing_returns_404(self, tbl):
        resp = crud.delete_bookmark(USER, "nonexistent-id")
        assert resp["statusCode"] == 404


# ══════════════════════════════════════════════════════════════════════════════
# Router
# ══════════════════════════════════════════════════════════════════════════════

class TestRouter:
    def test_list_route(self, tbl):
        resp = router.route("GET /bookmarks", USER, {}, {}, {})
        assert resp["statusCode"] == 200

    def test_create_route(self, tbl):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen()):
            resp = router.route("POST /bookmarks", USER, {"url": "https://example.com/"}, {}, {})
        assert resp["statusCode"] == 201

    def test_get_route_missing_id(self, tbl):
        resp = router.route("GET /bookmarks/{id}", USER, {}, {}, {})
        assert resp["statusCode"] == 400

    def test_unknown_route(self, tbl):
        resp = router.route("PATCH /bookmarks", USER, {}, {}, {})
        assert resp["statusCode"] == 404
