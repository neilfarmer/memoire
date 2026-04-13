"""Unit tests for lambda/feeds/crud.py and router.py."""

import json
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda, make_table

# ── env vars before module load ───────────────────────────────────────────────
os.environ["FEEDS_TABLE"]      = "test-feeds"
os.environ["FEEDS_READ_TABLE"] = "test-feeds-read"

crud   = load_lambda("feeds", "crud.py")
router = load_lambda("feeds", "router.py")

FEEDS_TABLE      = "test-feeds"
FEEDS_READ_TABLE = "test-feeds-read"

RSS_XML = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Article One</title>
      <link>https://example.com/1</link>
      <pubDate>Mon, 07 Apr 2026 00:00:00 +0000</pubDate>
      <description>Hello world</description>
    </item>
  </channel>
</rss>"""

ATOM_XML = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Feed</title>
  <entry>
    <title>Atom Article</title>
    <link rel="alternate" href="https://example.com/atom/1"/>
    <published>2026-04-07T00:00:00Z</published>
    <summary>Atom summary text</summary>
  </entry>
</feed>"""


def _mock_urlopen(body: bytes, status: int = 200, final_url: str = ""):
    resp = MagicMock()
    resp.read.return_value = body
    resp.geturl.return_value = final_url or "https://example.com/feed"
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


@pytest.fixture
def tbls():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, FEEDS_TABLE,      "user_id", "feed_id")
        make_table(ddb, FEEDS_READ_TABLE, "user_id", "article_url")
        yield ddb


# ══════════════════════════════════════════════════════════════════════════════
# Feed management
# ══════════════════════════════════════════════════════════════════════════════

class TestIsFeedRoot:
    def test_rss_tag(self):
        assert crud._is_feed_root("rss") is True

    def test_atom_feed_tag(self):
        assert crud._is_feed_root("feed") is True

    def test_namespaced_atom_tag(self):
        assert crud._is_feed_root("{http://www.w3.org/2005/Atom}feed") is True

    def test_rdf_tag(self):
        assert crud._is_feed_root("RDF") is True

    def test_sitemap_tag(self):
        assert crud._is_feed_root("urlset") is False

    def test_html_tag(self):
        assert crud._is_feed_root("html") is False


class TestIsSafeUrl:
    def test_public_ip_is_safe(self):
        with patch.object(crud.socket, "gethostbyname", return_value="93.184.216.34"):
            assert crud._is_safe_url("https://example.com/feed") is True

    def test_private_ip_is_unsafe(self):
        with patch.object(crud.socket, "gethostbyname", return_value="192.168.1.1"):
            assert crud._is_safe_url("https://internal.example.com/feed") is False

    def test_loopback_is_unsafe(self):
        with patch.object(crud.socket, "gethostbyname", return_value="127.0.0.1"):
            assert crud._is_safe_url("https://localhost/feed") is False

    def test_link_local_is_unsafe(self):
        with patch.object(crud.socket, "gethostbyname", return_value="169.254.169.254"):
            assert crud._is_safe_url("http://169.254.169.254/latest/meta-data/") is False

    def test_no_hostname_is_unsafe(self):
        assert crud._is_safe_url("not-a-url") is False


# Patch _is_safe_url to return True for all discover/fetch tests since
# they use mocked URLs that won't resolve in the test environment.
_safe_url_patch = patch.object(crud, "_is_safe_url", return_value=True)


class TestDiscoverFeedUrl:
    def test_valid_rss_feed_returns_url(self):
        mock = _mock_urlopen(RSS_XML, final_url="https://example.com/feed.rss")
        with _safe_url_patch, patch("urllib.request.urlopen", return_value=mock):
            url, err = crud._discover_feed_url("https://example.com/feed.rss")
        assert err is None
        assert url == "https://example.com/feed.rss"

    def test_returns_post_redirect_url(self):
        mock = _mock_urlopen(RSS_XML, final_url="https://cdn.example.com/feed.rss")
        with _safe_url_patch, patch("urllib.request.urlopen", return_value=mock):
            url, err = crud._discover_feed_url("https://example.com/feed")
        assert err is None
        assert url == "https://cdn.example.com/feed.rss"

    def test_non_feed_xml_returns_error(self):
        sitemap = b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>'
        with _safe_url_patch, patch("urllib.request.urlopen", return_value=_mock_urlopen(sitemap)):
            url, err = crud._discover_feed_url("https://example.com/sitemap.xml")
        assert url is None
        assert err == "No RSS or Atom feed found at that URL"

    def test_non_xml_page_autodiscovers_feed(self):
        html = (
            b'<html><head>'
            b'<link rel="alternate" type="application/rss+xml" href="https://example.com/feed.rss">'
            b'</head></html>'
        )
        feed_mock = _mock_urlopen(RSS_XML, final_url="https://example.com/feed.rss")
        def side_effect(req, timeout):
            if "feed.rss" in req.full_url:
                return feed_mock
            return _mock_urlopen(html, final_url="https://example.com/")
        with _safe_url_patch, patch("urllib.request.urlopen", side_effect=side_effect):
            url, err = crud._discover_feed_url("https://example.com/")
        assert err is None
        assert url == "https://example.com/feed.rss"

    def test_file_scheme_autodiscovery_skipped(self):
        html = (
            b'<html><head>'
            b'<link rel="alternate" type="application/rss+xml" href="file:///etc/passwd">'
            b'</head></html>'
        )
        with _safe_url_patch, patch("urllib.request.urlopen", return_value=_mock_urlopen(html)):
            url, err = crud._discover_feed_url("https://example.com/")
        assert url is None
        assert err == "No RSS or Atom feed found at that URL"

    def test_network_error_returns_error(self):
        with _safe_url_patch, patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            url, err = crud._discover_feed_url("https://example.com/feed.rss")
        assert url is None
        assert "Could not reach" in err

    def test_no_feed_found_returns_error(self):
        html = b'<html><body>No feed here</body></html>'
        with _safe_url_patch, patch("urllib.request.urlopen", return_value=_mock_urlopen(html)):
            url, err = crud._discover_feed_url("https://example.com/")
        assert url is None
        assert err == "No RSS or Atom feed found at that URL"

    def test_private_ip_rejected(self):
        with patch.object(crud, "_is_safe_url", return_value=False):
            url, err = crud._discover_feed_url("http://169.254.169.254/latest/")
        assert url is None
        assert "public IP" in err


class TestListFeeds:
    def test_empty_for_new_user(self, tbls):
        result = crud.list_feeds(USER)
        assert result["statusCode"] == 200
        assert json.loads(result["body"]) == []

    def test_returns_added_feeds(self, tbls):
        with patch.object(crud, "_discover_feed_url", side_effect=lambda u: (u, None)):
            crud.add_feed(USER, {"url": "https://example.com/feed.rss"})
        result = crud.list_feeds(USER)
        feeds = json.loads(result["body"])
        assert len(feeds) == 1
        assert feeds[0]["url"] == "https://example.com/feed.rss"


class TestAddFeed:
    def test_missing_url_returns_error(self, tbls):
        result = crud.add_feed(USER, {})
        assert result["statusCode"] == 400

    def test_invalid_scheme_returns_error(self, tbls):
        result = crud.add_feed(USER, {"url": "ftp://example.com"})
        assert result["statusCode"] == 400

    def test_adds_valid_feed(self, tbls):
        with patch.object(crud, "_discover_feed_url", side_effect=lambda u: (u, None)):
            result = crud.add_feed(USER, {"url": "https://example.com/feed.rss"})
        assert result["statusCode"] == 201
        body = json.loads(result["body"])
        assert body["url"] == "https://example.com/feed.rss"
        assert "feed_id" in body

    def test_duplicate_returns_error(self, tbls):
        url = "https://example.com/feed.rss"
        with patch.object(crud, "_discover_feed_url", side_effect=lambda u: (u, None)):
            crud.add_feed(USER, {"url": url})
            result = crud.add_feed(USER, {"url": url})
        assert result["statusCode"] == 400


class TestDeleteFeed:
    def test_missing_feed_returns_404(self, tbls):
        result = crud.delete_feed(USER, "nonexistent-id")
        assert result["statusCode"] == 404

    def test_deletes_existing_feed(self, tbls):
        with patch.object(crud, "_discover_feed_url", side_effect=lambda u: (u, None)):
            added = json.loads(crud.add_feed(USER, {"url": "https://example.com/f.rss"})["body"])
        result = crud.delete_feed(USER, added["feed_id"])
        assert result["statusCode"] == 204
        assert json.loads(crud.list_feeds(USER)["body"]) == []


# ══════════════════════════════════════════════════════════════════════════════
# Pure helper functions
# ══════════════════════════════════════════════════════════════════════════════

class TestParseDate:
    def test_empty_string(self):
        assert crud._parse_date("") == ""

    def test_rfc2822(self):
        result = crud._parse_date("Mon, 07 Apr 2026 00:00:00 +0000")
        assert "2026" in result

    def test_iso_format(self):
        result = crud._parse_date("2026-04-07T00:00:00Z")
        assert "2026" in result

    def test_unparseable_returns_original(self):
        assert crud._parse_date("not a date") == "not a date"


class TestStripHtml:
    def test_removes_tags(self):
        assert crud._strip_html("<p>Hello <b>world</b></p>") == "Hello  world"

    def test_empty_string(self):
        assert crud._strip_html("") == ""

    def test_none(self):
        assert crud._strip_html(None) == ""


class TestExtractFirstImg:
    def test_finds_src(self):
        html = '<img src="https://example.com/img.jpg" alt="test">'
        assert crud._extract_first_img(html) == "https://example.com/img.jpg"

    def test_empty_returns_empty(self):
        assert crud._extract_first_img("") == ""

    def test_no_img_returns_empty(self):
        assert crud._extract_first_img("<p>no image here</p>") == ""

    def test_html_escaped_content(self):
        html = "&lt;img src=&quot;https://example.com/x.png&quot;&gt;"
        assert crud._extract_first_img(html) == "https://example.com/x.png"


# ══════════════════════════════════════════════════════════════════════════════
# HTTP-dependent fetchers
# ══════════════════════════════════════════════════════════════════════════════

class TestFetchOgImage:
    def test_returns_og_image(self):
        html = b'<meta property="og:image" content="https://example.com/og.jpg">'
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(html)):
            result = crud._fetch_og_image("https://example.com/article")
        assert result == "https://example.com/og.jpg"

    def test_returns_twitter_image_fallback(self):
        html = b'<meta name="twitter:image" content="https://example.com/tw.jpg">'
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(html)):
            result = crud._fetch_og_image("https://example.com/article")
        assert result == "https://example.com/tw.jpg"

    def test_returns_empty_on_exception(self):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = crud._fetch_og_image("https://example.com/article")
        assert result == ""

    def test_empty_url_returns_empty(self):
        assert crud._fetch_og_image("") == ""


class TestFetchArticleText:
    def test_returns_text(self, tbls):
        html = b"<article><p>Hello world content here</p></article>"
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(html)):
            result = crud.fetch_article_text(USER, "https://example.com/a")
        assert result["statusCode"] == 200
        assert "Hello world" in json.loads(result["body"])["text"]

    def test_invalid_url_returns_error(self, tbls):
        result = crud.fetch_article_text(USER, "not-a-url")
        assert result["statusCode"] == 400

    def test_fetch_exception_returns_error(self, tbls):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = crud.fetch_article_text(USER, "https://example.com/a")
        assert result["statusCode"] == 400


class TestFetchFeed:
    def test_parses_rss(self):
        with _safe_url_patch, patch("urllib.request.urlopen", return_value=_mock_urlopen(RSS_XML)):
            articles = crud._fetch_feed("feed-1", "https://example.com/rss")
        assert len(articles) == 1
        assert articles[0]["title"] == "Article One"
        assert articles[0]["url"] == "https://example.com/1"
        assert articles[0]["feed_title"] == "Test Feed"

    def test_parses_atom(self):
        with _safe_url_patch, patch("urllib.request.urlopen", return_value=_mock_urlopen(ATOM_XML)):
            articles = crud._fetch_feed("feed-2", "https://example.com/atom")
        assert len(articles) == 1
        assert articles[0]["title"] == "Atom Article"

    def test_returns_empty_on_network_error(self):
        with _safe_url_patch, patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            articles = crud._fetch_feed("feed-1", "https://example.com/rss")
        assert articles == []

    def test_returns_empty_on_private_ip(self):
        with patch.object(crud, "_is_safe_url", return_value=False):
            articles = crud._fetch_feed("feed-1", "http://169.254.169.254/")
        assert articles == []

    def test_returns_empty_on_bad_xml(self):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(b"not xml")):
            articles = crud._fetch_feed("feed-1", "https://example.com/rss")
        assert articles == []


class TestGetArticlesWithFetch:
    def test_fetches_and_caches_when_no_cache(self, tbls):
        with patch.object(crud, "_discover_feed_url", side_effect=lambda u: (u, None)):
            crud.add_feed(USER, {"url": "https://example.com/rss"})
        with patch.object(crud, "_fetch_feed", return_value=[{
            "feed_id": "f1", "feed_title": "T", "title": "A",
            "url": "https://example.com/1", "description": "d",
            "image": "https://example.com/img.jpg", "published": "2026-04-07T00:00:00+00:00",
        }]):
            result = crud.get_articles(USER)
        assert result["statusCode"] == 200
        assert len(json.loads(result["body"])) == 1
        # Cache should now be set
        assert crud._get_cache(USER) is not None


# ══════════════════════════════════════════════════════════════════════════════
# Article cache
# ══════════════════════════════════════════════════════════════════════════════

class TestGetCache:
    def test_returns_none_when_no_item(self, tbls):
        assert crud._get_cache(USER) is None

    def test_returns_none_when_stale(self, tbls):
        stale_time = (datetime.now(timezone.utc) - timedelta(seconds=3601)).isoformat()
        crud._table().put_item(Item={
            "user_id":      USER,
            "feed_id":      crud.CACHE_ITEM_KEY,
            "articles":     json.dumps([{"title": "old"}]),
            "refreshed_at": stale_time,
        })
        assert crud._get_cache(USER) is None

    def test_returns_articles_when_fresh(self, tbls):
        articles = [{"title": "fresh article", "url": "https://example.com"}]
        crud._set_cache(USER, articles)
        assert crud._get_cache(USER) == articles


class TestSetCache:
    def test_stores_and_overwrites(self, tbls):
        crud._set_cache(USER, [{"title": "old"}])
        crud._set_cache(USER, [{"title": "new"}])
        assert crud._get_cache(USER) == [{"title": "new"}]


class TestGetArticlesCaching:
    def test_returns_cached_when_fresh(self, tbls):
        articles = [{"title": "cached", "url": "https://example.com"}]
        crud._set_cache(USER, articles)
        result = crud.get_articles(USER)
        assert json.loads(result["body"]) == articles

    def test_force_bypasses_cache(self, tbls):
        crud._set_cache(USER, [{"title": "stale"}])
        result = crud.get_articles(USER, force=True)
        assert result["statusCode"] == 200

    def test_cache_item_excluded_from_feed_list(self, tbls):
        crud._set_cache(USER, [])
        with patch.object(crud, "_fetch_feed", return_value=[]) as mock_fetch:
            crud.get_articles(USER, force=True)
            for call in mock_fetch.call_args_list:
                assert call.args[1] != crud.CACHE_ITEM_KEY


# ══════════════════════════════════════════════════════════════════════════════
# Read tracking
# ══════════════════════════════════════════════════════════════════════════════

class TestGetReadUrls:
    def test_empty_for_new_user(self, tbls):
        result = crud.get_read_urls(USER)
        assert json.loads(result["body"]) == []

    def test_returns_marked_urls(self, tbls):
        crud.mark_read(USER, {"url": "https://example.com/a"})
        crud.mark_read(USER, {"url": "https://example.com/b"})
        urls = json.loads(crud.get_read_urls(USER)["body"])
        assert set(urls) == {"https://example.com/a", "https://example.com/b"}


class TestMarkRead:
    def test_missing_url_returns_error(self, tbls):
        assert crud.mark_read(USER, {})["statusCode"] == 400

    def test_marks_url_as_read(self, tbls):
        result = crud.mark_read(USER, {"url": "https://example.com/a"})
        assert result["statusCode"] == 200
        item = crud._read_table().get_item(
            Key={"user_id": USER, "article_url": "https://example.com/a"}
        ).get("Item")
        assert item is not None
        assert "read_at" in item

    def test_idempotent(self, tbls):
        url = "https://example.com/a"
        crud.mark_read(USER, {"url": url})
        assert crud.mark_read(USER, {"url": url})["statusCode"] == 200


# ══════════════════════════════════════════════════════════════════════════════
# Router
# ══════════════════════════════════════════════════════════════════════════════

class TestRouter:
    def test_list_feeds(self, tbls):
        assert router.route("GET /feeds", USER, {}, {})["statusCode"] == 200

    def test_add_feed(self, tbls):
        with patch.object(crud, "_discover_feed_url", side_effect=lambda u: (u, None)):
            r = router.route("POST /feeds", USER, {"url": "https://example.com/f.rss"}, {})
        assert r["statusCode"] == 201

    def test_delete_feed(self, tbls):
        with patch.object(crud, "_discover_feed_url", side_effect=lambda u: (u, None)):
            added = json.loads(router.route("POST /feeds", USER, {"url": "https://x.com/f.rss"}, {})["body"])
        r = router.route("DELETE /feeds/{id}", USER, {}, {"id": added["feed_id"]})
        assert r["statusCode"] == 204

    def test_delete_missing_id(self, tbls):
        r = router.route("DELETE /feeds/{id}", USER, {}, {})
        assert r["statusCode"] == 400

    def test_get_articles(self, tbls):
        assert router.route("GET /feeds/articles", USER, {}, {})["statusCode"] == 200

    def test_get_articles_force(self, tbls):
        assert router.route("GET /feeds/articles", USER, {}, {"force": "true"})["statusCode"] == 200

    def test_fetch_article_text(self, tbls):
        html = b"<article>content</article>"
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(html)):
            r = router.route("GET /feeds/article-text", USER, {}, {"url": "https://example.com/a"})
        assert r["statusCode"] == 200

    def test_get_read(self, tbls):
        assert router.route("GET /feeds/read", USER, {}, {})["statusCode"] == 200

    def test_post_read(self, tbls):
        r = router.route("POST /feeds/read", USER, {"url": "https://example.com"}, {})
        assert r["statusCode"] == 200

    def test_post_read_missing_url(self, tbls):
        assert router.route("POST /feeds/read", USER, {}, {})["statusCode"] == 400

    def test_unknown_route(self, tbls):
        assert router.route("GET /feeds/unknown", USER, {}, {})["statusCode"] == 404
