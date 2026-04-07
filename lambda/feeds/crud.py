"""RSS Feeds CRUD and article fetching."""

import os
import re
import uuid
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

import urllib.parse

import db
from response import ok, created, no_content, error, not_found

FEEDS_TABLE      = os.environ["FEEDS_TABLE"]
FEEDS_READ_TABLE = os.environ["FEEDS_READ_TABLE"]

MEDIA_NS   = "http://search.yahoo.com/mrss/"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
ATOM_NS    = "http://www.w3.org/2005/Atom"

MAX_FEEDS       = 20
MAX_ARTICLES    = 100
FETCH_TIMEOUT   = 8
MAX_WORKERS     = 5
MAX_DESCRIPTION = 300


def _table():
    return db.get_table(FEEDS_TABLE)


def _read_table():
    return db.get_table(FEEDS_READ_TABLE)


# ── Feed management ───────────────────────────────────────────────────────────

def list_feeds(user_id: str) -> dict:
    items = db.query_by_user(_table(), user_id)
    items.sort(key=lambda x: x.get("created_at", ""))
    return ok(items)


def add_feed(user_id: str, body: dict) -> dict:
    url = (body.get("url") or "").strip()
    if not url:
        return error("url is required")
    if not url.startswith(("http://", "https://")):
        return error("url must start with http:// or https://")

    existing = db.query_by_user(_table(), user_id)
    if len(existing) >= MAX_FEEDS:
        return error(f"Maximum of {MAX_FEEDS} feeds allowed")
    if any(f["url"] == url for f in existing):
        return error("Feed URL already added")

    feed_id = str(uuid.uuid4())
    item = {
        "user_id":    user_id,
        "feed_id":    feed_id,
        "url":        url,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _table().put_item(Item=item)
    return created(item)


def delete_feed(user_id: str, feed_id: str) -> dict:
    existing = db.get_item(_table(), user_id, "feed_id", feed_id)
    if not existing:
        return not_found("Feed")
    db.delete_item(_table(), user_id, "feed_id", feed_id)
    return no_content()


# ── Article fetching ──────────────────────────────────────────────────────────

def _parse_date(s: str) -> str:
    if not s:
        return ""
    try:
        return parsedate_to_datetime(s.strip()).isoformat()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(s.strip().replace("Z", "+00:00")).isoformat()
    except Exception:
        return s


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html or "").strip()


def _extract_first_img(html: str) -> str:
    """Extract first img src from HTML, handling both raw and HTML-escaped content."""
    if not html:
        return ""
    import html as html_module
    # Try raw HTML first, then unescape and try again
    for content in (html, html_module.unescape(html)):
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content, re.IGNORECASE)
        if m:
            return m.group(1)
    return ""


def _fetch_og_image(url: str) -> str:
    """Fetch article page and extract an image URL. Returns empty string on failure."""
    if not url:
        return ""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (compatible; Memoire/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            chunk = resp.read(65_536).decode("utf-8", errors="ignore")

        # Try og:image (quoted and unquoted attribute values)
        patterns = [
            r'<meta[^>]+property=["\']?og:image["\']?[^>]+content=["\']?([^"\'>\s]+)',
            r'<meta[^>]+content=["\']?([^"\'>\s]+)["\']?[^>]+property=["\']?og:image',
            r'<meta[^>]+name=["\']?twitter:image["\']?[^>]+content=["\']?([^"\'>\s]+)',
            r'<meta[^>]+content=["\']?([^"\'>\s]+)["\']?[^>]+name=["\']?twitter:image',
        ]
        for pattern in patterns:
            m = re.search(pattern, chunk, re.IGNORECASE)
            if m:
                img = m.group(1).strip().rstrip('"\'')
                if img.startswith("http"):
                    return img
                if img.startswith("/"):
                    return urllib.parse.urljoin(url, img)

        # Last resort: first <img> inside the article body with a reasonable src
        body_match = re.search(r'<(?:article|main|div[^>]+class=["\'][^"\']*(?:content|post|body|entry)[^"\']*["\'])[^>]*>(.*)', chunk, re.IGNORECASE | re.DOTALL)
        search_area = body_match.group(1) if body_match else chunk
        img_m = re.search(r'<img[^>]+src=["\']?(https://[^"\'>\s]+\.(jpg|jpeg|png|webp|gif|svg))', search_area, re.IGNORECASE)
        if img_m:
            return img_m.group(1)

        return ""
    except Exception:
        return ""


MAX_ARTICLE_CHARS = 8_000  # ~2k tokens, enough for summarization


def fetch_article_text(user_id: str, url: str) -> dict:  # noqa: ARG001
    """Fetch an article URL and return extracted plain text for summarization."""
    if not url or not url.startswith("http"):
        return error("Invalid URL")
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (compatible; Memoire/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read(200_000).decode("utf-8", errors="ignore")

        # Strip script/style blocks
        html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
        # Try to isolate the article body
        body_m = re.search(
            r"<(?:article|main)[^>]*>(.*?)</(?:article|main)>",
            html, re.IGNORECASE | re.DOTALL
        )
        text_html = body_m.group(1) if body_m else html
        # Strip remaining tags
        text = re.sub(r"<[^>]+>", " ", text_html)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        text = text[:MAX_ARTICLE_CHARS]
        return ok({"text": text, "url": url})
    except Exception:
        return error("Could not fetch article")


def _find_image(element) -> str:
    """Try common RSS image locations on an item/entry element."""
    # media:thumbnail
    el = element.find(f"{{{MEDIA_NS}}}thumbnail")
    if el is not None and el.get("url"):
        return el.get("url")
    # media:content (image type)
    for el in element.findall(f"{{{MEDIA_NS}}}content"):
        if el.get("url") and (el.get("medium") == "image" or
                               (el.get("type") or "").startswith("image")):
            return el.get("url")
        if el.get("url") and not el.get("medium") and not el.get("type"):
            return el.get("url")
    # enclosure (image type)
    el = element.find("enclosure")
    if el is not None and (el.get("type") or "").startswith("image"):
        return el.get("url", "")
    return ""


def _fetch_feed(feed_id: str, url: str) -> list[dict]:
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Memoire/1.0 RSS Reader"}
        )
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            content = resp.read(1_000_000)  # cap at 1MB
    except Exception:
        return []

    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []

    articles = []
    tag = root.tag

    if tag == f"{{{ATOM_NS}}}feed" or tag == "feed":
        # Atom
        ns = ATOM_NS if tag.startswith("{") else ""
        def at(t):
            return f"{{{ns}}}{t}" if ns else t

        feed_title = root.findtext(at("title")) or url

        for entry in root.findall(at("entry")):
            title = entry.findtext(at("title")) or ""
            link_el = entry.find(f"{{{ATOM_NS}}}link[@rel='alternate']") or entry.find(at("link"))
            article_url = link_el.get("href", "") if link_el is not None else ""
            published = _parse_date(
                entry.findtext(at("published")) or entry.findtext(at("updated")) or ""
            )
            summary = entry.findtext(at("summary")) or entry.findtext(at("content")) or ""
            image = _find_image(entry) or _extract_first_img(summary)

            articles.append({
                "feed_id":    feed_id,
                "feed_title": feed_title,
                "title":      title.strip(),
                "url":        article_url,
                "description": _strip_html(summary)[:MAX_DESCRIPTION],
                "image":      image,
                "published":  published,
            })
    else:
        # RSS 2.0
        channel = root.find("channel")
        if channel is None:
            return []
        feed_title = channel.findtext("title") or url

        for item in channel.findall("item"):
            title       = item.findtext("title") or ""
            article_url = item.findtext("link") or ""
            published   = _parse_date(item.findtext("pubDate") or "")
            description = (
                item.findtext(f"{{{CONTENT_NS}}}encoded") or
                item.findtext("description") or ""
            )
            image = _find_image(item) or _extract_first_img(description)

            articles.append({
                "feed_id":    feed_id,
                "feed_title": feed_title,
                "title":      title.strip(),
                "url":        article_url,
                "description": _strip_html(description)[:MAX_DESCRIPTION],
                "image":      image,
                "published":  published,
            })

    return articles


def get_articles(user_id: str) -> dict:
    feeds = db.query_by_user(_table(), user_id)
    if not feeds:
        return ok([])

    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    all_articles: list[dict] = []
    workers = min(len(feeds), MAX_WORKERS)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_fetch_feed, f["feed_id"], f["url"]) for f in feeds]
        for future in futures:
            try:
                all_articles.extend(future.result(timeout=12))
            except Exception:
                pass

    # Filter to last 30 days and sort descending
    recent = [a for a in all_articles if a.get("published", "") >= cutoff]
    recent.sort(key=lambda x: x.get("published", ""), reverse=True)
    recent = recent[:MAX_ARTICLES]

    # For articles without images, attempt to fetch og:image from the article page
    no_image = [a for a in recent if not a.get("image") and a.get("url")]
    if no_image:
        og_workers = min(len(no_image), 8)
        with ThreadPoolExecutor(max_workers=og_workers) as executor:
            futures = {executor.submit(_fetch_og_image, a["url"]): a for a in no_image}
            for future, article in futures.items():
                try:
                    img = future.result(timeout=5)
                    if img:
                        article["image"] = img
                except Exception:
                    pass

    return ok(recent)


# ── Read tracking ─────────────────────────────────────────────────────────────

def get_read_urls(user_id: str) -> dict:
    items = db.query_by_user(_read_table(), user_id)
    return ok([item["article_url"] for item in items])


def mark_read(user_id: str, body: dict) -> dict:
    url = (body.get("url") or "").strip()
    if not url:
        return error("url is required")
    _read_table().put_item(Item={
        "user_id":     user_id,
        "article_url": url,
        "read_at":     datetime.now(timezone.utc).isoformat(),
    })
    return ok({"url": url})
