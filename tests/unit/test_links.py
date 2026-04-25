"""Unit tests for lambda/layer/python/links_util.py and lambda/links/."""

import json
import os

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda, make_links_table

# LINKS_TABLE is preset in conftest. Import links_util through the shared layer
# path load_lambda uses, so writers and this module share the same instance.
load_lambda("links", "crud.py")  # registers layer modules + links_util
import links_util  # noqa: E402

TABLE_NAME = os.environ["LINKS_TABLE"]


@pytest.fixture
def tbl():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_links_table(ddb, TABLE_NAME)
        yield ddb


# ══════════════════════════════════════════════════════════════════════════════
# Parsing
# ══════════════════════════════════════════════════════════════════════════════

class TestParseWikiLinks:
    def test_single_link(self):
        assert links_util.parse_wiki_links("See [[note:abc-123]]") == [("note", "abc-123")]

    def test_multiple_types(self):
        text = "Ref [[task:t1]] and [[note:n1]] and [[goal:g1]]"
        assert links_util.parse_wiki_links(text) == [
            ("task", "t1"), ("note", "n1"), ("goal", "g1"),
        ]

    def test_deduplicates_preserving_order(self):
        text = "[[note:a]] then [[note:b]] then [[note:a]]"
        assert links_util.parse_wiki_links(text) == [("note", "a"), ("note", "b")]

    def test_journal_date_id(self):
        assert links_util.parse_wiki_links("[[journal:2026-04-24]]") == [("journal", "2026-04-24")]

    def test_unknown_type_dropped(self):
        assert links_util.parse_wiki_links("[[foo:bar]] [[note:ok]]") == [("note", "ok")]

    def test_empty_and_none(self):
        assert links_util.parse_wiki_links("") == []
        assert links_util.parse_wiki_links(None) == []

    def test_malformed_not_matched(self):
        assert links_util.parse_wiki_links("[[note:abc") == []
        assert links_util.parse_wiki_links("[[note]]") == []
        assert links_util.parse_wiki_links("[note:abc]") == []


# ══════════════════════════════════════════════════════════════════════════════
# sync_links — outbound persistence + dedup + reconciliation
# ══════════════════════════════════════════════════════════════════════════════

class TestSyncLinks:
    def test_creates_outbound_rows(self, tbl):
        links_util.sync_links(USER, "note", "n1", ["Mentions [[task:t1]] and [[goal:g9]]"])
        edges = links_util.query_outbound(USER, "note", "n1")
        keys = sorted(e["link_key"] for e in edges)
        assert keys == [
            "note#n1#goal#g9",
            "note#n1#task#t1",
        ]
        assert {e["target_key"] for e in edges} == {"task#t1", "goal#g9"}

    def test_dedups_duplicate_references(self, tbl):
        links_util.sync_links(
            USER, "note", "n1",
            ["[[task:t1]]", "[[task:t1]] again [[task:t1]]"],
        )
        edges = links_util.query_outbound(USER, "note", "n1")
        assert len(edges) == 1

    def test_reconciliation_removes_stale(self, tbl):
        links_util.sync_links(USER, "note", "n1", ["[[task:t1]] [[task:t2]]"])
        assert len(links_util.query_outbound(USER, "note", "n1")) == 2

        links_util.sync_links(USER, "note", "n1", ["[[task:t1]] [[task:t3]]"])
        edges = links_util.query_outbound(USER, "note", "n1")
        keys = sorted(e["link_key"] for e in edges)
        assert keys == ["note#n1#task#t1", "note#n1#task#t3"]

    def test_self_reference_dropped(self, tbl):
        links_util.sync_links(USER, "note", "n1", ["Meta: [[note:n1]] and [[note:n2]]"])
        edges = links_util.query_outbound(USER, "note", "n1")
        assert len(edges) == 1
        assert edges[0]["target_id"] == "n2"

    def test_empty_texts_clears_links(self, tbl):
        links_util.sync_links(USER, "note", "n1", ["[[task:t1]]"])
        assert len(links_util.query_outbound(USER, "note", "n1")) == 1
        links_util.sync_links(USER, "note", "n1", [""])
        assert links_util.query_outbound(USER, "note", "n1") == []

    def test_delete_source_links(self, tbl):
        links_util.sync_links(USER, "note", "n1", ["[[task:t1]] [[task:t2]]"])
        links_util.delete_source_links(USER, "note", "n1")
        assert links_util.query_outbound(USER, "note", "n1") == []


# ══════════════════════════════════════════════════════════════════════════════
# Reverse lookup via the GSI
# ══════════════════════════════════════════════════════════════════════════════

class TestReverseLookup:
    def test_inbound_finds_all_sources(self, tbl):
        links_util.sync_links(USER, "note",    "n1", ["[[task:t1]]"])
        links_util.sync_links(USER, "note",    "n2", ["[[task:t1]]"])
        links_util.sync_links(USER, "journal", "2026-04-24", ["[[task:t1]]"])

        inbound = links_util.query_inbound(USER, "task", "t1")
        sources = sorted((e["source_type"], e["source_id"]) for e in inbound)
        assert sources == [
            ("journal", "2026-04-24"),
            ("note",    "n1"),
            ("note",    "n2"),
        ]

    def test_inbound_scoped_by_target(self, tbl):
        links_util.sync_links(USER, "note", "n1", ["[[task:t1]] [[task:t2]]"])
        inbound_t1 = links_util.query_inbound(USER, "task", "t1")
        inbound_t2 = links_util.query_inbound(USER, "task", "t2")
        assert len(inbound_t1) == 1 and inbound_t1[0]["target_id"] == "t1"
        assert len(inbound_t2) == 1 and inbound_t2[0]["target_id"] == "t2"

    def test_inbound_scoped_by_user(self, tbl):
        links_util.sync_links("userA", "note", "nA", ["[[task:shared]]"])
        links_util.sync_links("userB", "note", "nB", ["[[task:shared]]"])
        assert [e["source_id"] for e in links_util.query_inbound("userA", "task", "shared")] == ["nA"]
        assert [e["source_id"] for e in links_util.query_inbound("userB", "task", "shared")] == ["nB"]


# ══════════════════════════════════════════════════════════════════════════════
# Links Lambda router + crud
# ══════════════════════════════════════════════════════════════════════════════

links_router = load_lambda("links", "router.py")


class TestLinksRouter:
    def test_outbound_requires_source_type(self, tbl):
        resp = links_router.route("GET /links", USER, {}, {}, {})
        assert resp["statusCode"] == 400

    def test_outbound_rejects_unknown_type(self, tbl):
        resp = links_router.route(
            "GET /links", USER, {}, {},
            {"source_type": "mystery", "source_id": "x"},
        )
        assert resp["statusCode"] == 400

    def test_outbound_requires_source_id(self, tbl):
        resp = links_router.route(
            "GET /links", USER, {}, {},
            {"source_type": "note"},
        )
        assert resp["statusCode"] == 400

    def test_outbound_happy_path(self, tbl):
        links_util.sync_links(USER, "note", "n1", ["[[task:t1]]"])
        resp = links_router.route(
            "GET /links", USER, {}, {},
            {"source_type": "note", "source_id": "n1"},
        )
        assert resp["statusCode"] == 200
        edges = json.loads(resp["body"])
        assert len(edges) == 1
        assert edges[0]["target_type"] == "task"

    def test_backlinks_happy_path(self, tbl):
        links_util.sync_links(USER, "note", "n1", ["[[task:t1]]"])
        resp = links_router.route(
            "GET /backlinks", USER, {}, {},
            {"target_type": "task", "target_id": "t1"},
        )
        assert resp["statusCode"] == 200
        edges = json.loads(resp["body"])
        assert [e["source_id"] for e in edges] == ["n1"]

    def test_unknown_route(self, tbl):
        resp = links_router.route("POST /links", USER, {}, {}, {})
        assert resp["statusCode"] == 404
