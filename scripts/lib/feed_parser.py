"""Parse RSS/Atom feed XML and blog-style HTML pages into entry dicts."""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

from .parsing import strip_html


def _detect_namespaces(xml_text: str) -> dict[str, str]:
    ns: dict[str, str] = {}
    for _event, (prefix, uri) in ET.iterparse(
        io.StringIO(xml_text), events=["start-ns"]
    ):
        if prefix:
            ns[prefix] = uri
        elif "atom" not in ns and "Atom" in uri:
            ns["atom"] = uri
    return ns


def parse_feed(xml_text: str, source_name: str, category: str) -> list[dict[str, Any]]:
    """Parse an RSS 2.0 / RDF / Atom feed into a list of entry dicts.

    Each entry has the keys: ``title``, ``link``, ``date``, ``content``,
    ``source``, ``category``. ``date`` is the raw string from the feed
    (``None`` if absent); call ``lib.parsing.parse_date`` to convert.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        print(f"  XML parse error for {source_name}: {exc}")
        return []

    ns = _detect_namespaces(xml_text)
    root_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

    if root_tag == "feed":
        return _parse_atom(root, source_name, category, ns)
    if root_tag in ("rss", "RDF"):
        return _parse_rss(root, source_name, category, ns)

    # Unknown root: try both.
    entries = _parse_rss(root, source_name, category, ns)
    if not entries:
        entries = _parse_atom(root, source_name, category, ns)
    return entries


def _find(elem: ET.Element, paths: list[str], ns: dict[str, str]) -> ET.Element | None:
    for path in paths:
        result = elem.find(path, ns)
        if result is not None:
            return result
    return None


def _parse_atom(
    root: ET.Element, source_name: str, category: str, ns: dict[str, str]
) -> list[dict[str, Any]]:
    atom_ns = ns.get("atom", "")
    items: list[ET.Element] = []
    if atom_ns:
        items = root.findall(f"{{{atom_ns}}}entry")
        if not items:
            items = root.findall(f".//{{{atom_ns}}}entry")
    if not items:
        items = root.findall(".//entry")

    entries: list[dict[str, Any]] = []
    for entry in items:
        title_el = _find(
            entry,
            [
                f"{{{atom_ns}}}title" if atom_ns else "title",
                "title",
            ],
            ns,
        )
        title = (title_el.text or "Untitled") if title_el is not None else "Untitled"

        link = ""
        link_tag = f"{{{atom_ns}}}link" if atom_ns else "link"
        for link_el in entry.findall(link_tag):
            if link_el.get("rel", "alternate") == "alternate":
                link = link_el.get("href", "")
                break
        if not link:
            link_el = entry.find(link_tag)
            if link_el is not None:
                link = link_el.get("href", "")

        date_el = _find(
            entry,
            [
                f"{{{atom_ns}}}published" if atom_ns else "published",
                "published",
                f"{{{atom_ns}}}updated" if atom_ns else "updated",
                "updated",
            ],
            ns,
        )
        date_str = date_el.text if date_el is not None else None

        content_el = _find(
            entry,
            [
                f"{{{atom_ns}}}content" if atom_ns else "content",
                "content",
                f"{{{atom_ns}}}summary" if atom_ns else "summary",
                "summary",
            ],
            ns,
        )
        content = (content_el.text or "") if content_el is not None else ""

        entries.append(
            {
                "title": title.strip(),
                "link": link,
                "date": date_str,
                "content": strip_html(content),
                "source": source_name,
                "category": category,
            }
        )
    return entries


def _parse_rss(
    root: ET.Element, source_name: str, category: str, ns: dict[str, str]
) -> list[dict[str, Any]]:
    content_ns = ns.get("content", "http://purl.org/rss/1.0/modules/content/")
    entries: list[dict[str, Any]] = []

    for item in root.findall(".//item"):
        title_el = item.find("title")
        title = (title_el.text or "Untitled") if title_el is not None else "Untitled"

        link_el = item.find("link")
        link = ""
        if link_el is not None:
            link = link_el.text or (link_el.tail or "").strip()

        date_el = item.find("pubDate")
        if date_el is None and "dc" in ns:
            date_el = item.find("dc:date", ns)
        date_str = date_el.text if date_el is not None else None

        content_el = item.find(f"{{{content_ns}}}encoded")
        if content_el is None:
            content_el = item.find("description")
        content = (content_el.text or "") if content_el is not None else ""

        entries.append(
            {
                "title": title.strip(),
                "link": (link.strip() if link else ""),
                "date": date_str,
                "content": strip_html(content),
                "source": source_name,
                "category": category,
            }
        )
    return entries


# ---------------------------------------------------------------------------
# Blog-page link extraction
# ---------------------------------------------------------------------------


class BlogLinkExtractor(HTMLParser):
    """Best-effort extraction of article links from a blog index page."""

    ARTICLE_PATTERNS = [
        r"/blog/",
        r"/posts?/",
        r"/articles?/",
        r"/\d{4}/",  # year in URL like /2026/
        r"/writing/",
        r"/notes?/",
        r"/research/",
    ]

    EXCLUDE_PATTERNS = [
        r"\.(css|js|png|jpg|svg|ico|woff|xml|json)",
        r"/(tag|category|page|author|feed|rss|atom|search|about|contact|archive)(/|$)",
        r"^#",
        r"^mailto:",
        r"^javascript:",
    ]

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: list[dict[str, str]] = []
        self._current_link: dict[str, str] | None = None
        self._current_text: list[str] = []
        self._in_nav = False
        self._in_header = False
        self._in_footer = False
        self._nav_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag == "nav":
            self._in_nav = True
            self._nav_depth += 1
        elif tag == "header":
            self._in_header = True
        elif tag == "footer":
            self._in_footer = True

        if tag == "a" and not self._in_nav and not self._in_footer:
            href = attrs_dict.get("href", "")
            if href:
                self._current_link = {"href": href}
                self._current_text = []

    def handle_endtag(self, tag):
        if tag == "nav":
            self._nav_depth -= 1
            if self._nav_depth <= 0:
                self._in_nav = False
                self._nav_depth = 0
        elif tag == "header":
            self._in_header = False
        elif tag == "footer":
            self._in_footer = False

        if tag == "a" and self._current_link:
            text = " ".join(self._current_text).strip()
            if text and len(text) > 5:
                self._current_link["title"] = text
                self.links.append(self._current_link)
            self._current_link = None
            self._current_text = []

    def handle_data(self, data):
        if self._current_link is not None:
            self._current_text.append(data.strip())

    def get_article_links(self, max_entries: int = 10) -> list[dict[str, str]]:
        """Filter and return likely article links."""
        seen_urls: set[str] = set()
        articles: list[dict[str, str]] = []

        for link in self.links:
            href = link.get("href", "")
            title = link.get("title", "")

            full_url = urljoin(self.base_url, href)

            if full_url in seen_urls:
                continue
            if any(re.search(p, href, re.I) for p in self.EXCLUDE_PATTERNS):
                continue

            is_article = any(re.search(p, href, re.I) for p in self.ARTICLE_PATTERNS)
            if not is_article:
                if re.match(r"^/[a-z0-9][\w-]{3,}", href, re.I):
                    is_article = True
                elif self.base_url.rstrip("/") in full_url and href != "/" and len(href) > 5:
                    is_article = True

            if is_article and title:
                seen_urls.add(full_url)
                articles.append({"title": title[:200], "link": full_url})
                if len(articles) >= max_entries:
                    break

        return articles


def parse_web_page(
    html_text: str, source_name: str, category: str, base_url: str
) -> list[dict[str, Any]]:
    """Extract article-like entries from an HTML blog index page."""
    extractor = BlogLinkExtractor(base_url)
    try:
        extractor.feed(html_text)
    except Exception as exc:
        print(f"  HTML parse error for {source_name}: {exc}")
        return []

    return [
        {
            "title": art["title"],
            "link": art["link"],
            "date": None,
            "content": "",
            "source": source_name,
            "category": category,
        }
        for art in extractor.get_article_links(max_entries=10)
    ]
