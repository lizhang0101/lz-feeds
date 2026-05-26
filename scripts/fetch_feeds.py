#!/usr/bin/env python3
"""Fetch RSS/Atom feeds and extract recent entries.

Usage:
    python fetch_feeds.py [--hours N] [--sources PATH] [--output PATH]

Defaults:
    --hours 24
    --sources ../sources.yaml
    --output /tmp/feed_entries.json
"""
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor
import re
import json
import html
import argparse
import yaml


def fetch_url(url: str) -> str | None:
    try:
        result = subprocess.run(
            ["curl", "-sL", "--max-time", "15", "-A",
             "Mozilla/5.0 (compatible; FeedBot/1.0)", url],
            capture_output=True, text=True, timeout=20
        )
        return result.stdout if result.returncode == 0 else None
    except Exception:
        return None


def parse_date(date_str: str) -> datetime | None:
    if not date_str:
        return None
    date_str = date_str.strip()

    # ISO 8601 with colon in timezone offset (Python < 3.11 can't handle it)
    date_str_fixed = re.sub(r'(\d{2}):(\d{2})$', r'\1\2', date_str)

    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d",
    ]
    for s in (date_str, date_str_fixed):
        for fmt in formats:
            try:
                dt = datetime.strptime(s, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
    return None


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:2000]


def parse_feed(xml_text: str, source_name: str, category: str) -> list[dict]:
    """Parse both RSS and Atom feeds, handling namespaces properly."""
    entries = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"  XML parse error for {source_name}: {e}")
        return entries

    # Detect namespaces
    ns = {}
    for event, elem in ET.iterparse(__import__('io').StringIO(xml_text), events=['start-ns']):
        prefix, uri = elem
        if prefix:
            ns[prefix] = uri
        elif 'atom' not in ns and 'Atom' in uri:
            ns['atom'] = uri

    # Determine feed type by root tag
    root_tag = root.tag.split('}')[-1] if '}' in root.tag else root.tag

    if root_tag == 'feed':
        entries = _parse_atom(root, source_name, category, ns)
    elif root_tag in ('rss', 'RDF'):
        entries = _parse_rss(root, source_name, category, ns)
    else:
        # Try both
        entries = _parse_rss(root, source_name, category, ns)
        if not entries:
            entries = _parse_atom(root, source_name, category, ns)

    return entries


def _find(elem, paths: list[str], ns: dict) -> ET.Element | None:
    """Try multiple XPath expressions to find an element."""
    for path in paths:
        result = elem.find(path, ns)
        if result is not None:
            return result
    return None


def _parse_atom(root, source_name: str, category: str, ns: dict) -> list[dict]:
    entries = []
    # Find entry elements with or without namespace
    atom_ns = ns.get('atom', '')
    items = root.findall(f'{{{atom_ns}}}entry') if atom_ns else []
    if not items:
        items = root.findall('.//entry')
    if not items:
        items = root.findall(f'.//{{{atom_ns}}}entry') if atom_ns else []

    for entry in items:
        # Title
        title_el = _find(entry, [
            f'{{{atom_ns}}}title' if atom_ns else 'title',
            'title',
        ], ns)
        title = (title_el.text or "Untitled") if title_el is not None else "Untitled"

        # Link
        link = ""
        for link_el in entry.findall(f'{{{atom_ns}}}link' if atom_ns else 'link'):
            rel = link_el.get('rel', 'alternate')
            if rel == 'alternate':
                link = link_el.get('href', '')
                break
        if not link:
            link_el = entry.find(f'{{{atom_ns}}}link' if atom_ns else 'link')
            if link_el is not None:
                link = link_el.get('href', '')

        # Date
        date_el = _find(entry, [
            f'{{{atom_ns}}}published' if atom_ns else 'published',
            'published',
            f'{{{atom_ns}}}updated' if atom_ns else 'updated',
            'updated',
        ], ns)
        date_str = date_el.text if date_el is not None else None

        # Content
        content_el = _find(entry, [
            f'{{{atom_ns}}}content' if atom_ns else 'content',
            'content',
            f'{{{atom_ns}}}summary' if atom_ns else 'summary',
            'summary',
        ], ns)
        content = (content_el.text or "") if content_el is not None else ""

        entries.append({
            "title": title.strip(),
            "link": link,
            "date": date_str,
            "content": strip_html(content),
            "source": source_name,
            "category": category,
        })

    return entries


def _parse_rss(root, source_name: str, category: str, ns: dict) -> list[dict]:
    entries = []
    # Handle content:encoded namespace
    content_ns = ns.get('content', 'http://purl.org/rss/1.0/modules/content/')

    items = root.findall('.//item')

    for item in items:
        title_el = item.find('title')
        title = (title_el.text or "Untitled") if title_el is not None else "Untitled"

        link_el = item.find('link')
        link = ""
        if link_el is not None:
            link = link_el.text or (link_el.tail or "").strip()

        date_el = item.find('pubDate')
        if date_el is None:
            date_el = item.find('dc:date', ns) if 'dc' in ns else None
        date_str = date_el.text if date_el is not None else None

        # Try content:encoded first, then description
        content_el = item.find(f'{{{content_ns}}}encoded')
        if content_el is None:
            content_el = item.find('description')
        content = (content_el.text or "") if content_el is not None else ""

        entries.append({
            "title": title.strip(),
            "link": link.strip() if link else "",
            "date": date_str,
            "content": strip_html(content),
            "source": source_name,
            "category": category,
        })

    return entries


class BlogLinkExtractor(HTMLParser):
    """Extract article links from a blog's HTML page."""

    # Common patterns for blog post URLs
    ARTICLE_PATTERNS = [
        r'/blog/',
        r'/posts?/',
        r'/articles?/',
        r'/\d{4}/',  # year in URL like /2026/
        r'/writing/',
        r'/notes?/',
        r'/research/',
    ]

    # Patterns to exclude (navigation, assets, etc.)
    EXCLUDE_PATTERNS = [
        r'\.(css|js|png|jpg|svg|ico|woff|xml|json)',
        r'/(tag|category|page|author|feed|rss|atom|search|about|contact|archive)(/|$)',
        r'^#',
        r'^mailto:',
        r'^javascript:',
    ]

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: list[dict] = []
        self._current_link: dict | None = None
        self._current_text: list[str] = []
        self._in_nav = False
        self._in_header = False
        self._in_footer = False
        self._nav_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        # Track nav/header/footer to skip navigation links
        if tag in ('nav', 'header', 'footer'):
            if tag == 'nav':
                self._in_nav = True
                self._nav_depth += 1
            elif tag == 'header':
                self._in_header = True
            elif tag == 'footer':
                self._in_footer = True

        if tag == 'a' and not self._in_nav and not self._in_footer:
            href = attrs_dict.get('href', '')
            if href:
                self._current_link = {"href": href}
                self._current_text = []

    def handle_endtag(self, tag):
        if tag == 'nav':
            self._nav_depth -= 1
            if self._nav_depth <= 0:
                self._in_nav = False
                self._nav_depth = 0
        elif tag == 'header':
            self._in_header = False
        elif tag == 'footer':
            self._in_footer = False

        if tag == 'a' and self._current_link:
            text = ' '.join(self._current_text).strip()
            if text and len(text) > 5:  # skip very short link text
                self._current_link["title"] = text
                self.links.append(self._current_link)
            self._current_link = None
            self._current_text = []

    def handle_data(self, data):
        if self._current_link is not None:
            self._current_text.append(data.strip())

    def get_article_links(self, max_entries: int = 10) -> list[dict]:
        """Filter and return likely article links."""
        seen_urls = set()
        articles = []

        for link in self.links:
            href = link.get("href", "")
            title = link.get("title", "")

            # Resolve relative URLs
            full_url = urljoin(self.base_url, href)

            # Skip duplicates
            if full_url in seen_urls:
                continue

            # Skip excluded patterns
            if any(re.search(p, href, re.I) for p in self.EXCLUDE_PATTERNS):
                continue

            # Must match at least one article pattern OR be a path on the same domain
            is_article = any(re.search(p, href, re.I) for p in self.ARTICLE_PATTERNS)

            # Also accept links that look like standalone pages on the same domain
            if not is_article:
                # Accept if it's a relative path with meaningful slug
                if re.match(r'^/[a-z0-9][\w-]{3,}', href, re.I):
                    is_article = True
                # Accept if same domain with a path
                elif self.base_url.rstrip('/') in full_url and href != '/' and len(href) > 5:
                    is_article = True

            if is_article and title:
                seen_urls.add(full_url)
                articles.append({
                    "title": title[:200],
                    "link": full_url,
                })

                if len(articles) >= max_entries:
                    break

        return articles


def parse_web_page(html_text: str, source_name: str, category: str, base_url: str) -> list[dict]:
    """Extract article entries from an HTML blog page."""
    extractor = BlogLinkExtractor(base_url)
    try:
        extractor.feed(html_text)
    except Exception as e:
        print(f"  HTML parse error for {source_name}: {e}")
        return []

    articles = extractor.get_article_links(max_entries=10)
    entries = []
    for art in articles:
        entries.append({
            "title": art["title"],
            "link": art["link"],
            "date": None,  # web pages usually don't have per-link dates on list page
            "content": "",
            "source": source_name,
            "category": category,
        })

    return entries


def load_sources(path: Path) -> list[dict]:
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get('sources', []) or []


def get_seen_urls(feeds_dir: Path, today: str) -> set[str]:
    """Return all URLs mentioned in the most recent previous digest."""
    seen: set[str] = set()
    try:
        files = sorted(feeds_dir.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].md"))
        prev = [f for f in files if f.stem != today]
        if not prev:
            return seen
        content = prev[-1].read_text(encoding="utf-8")
        seen.update(re.findall(r'\]\((https?://[^)]+)\)', content))
    except Exception:
        pass
    return seen


def load_web_cache(cache_path: Path) -> dict[str, list[str]]:
    """Load cached URLs for web sources."""
    if cache_path.exists():
        with open(cache_path) as f:
            return json.load(f)
    return {}


def save_web_cache(cache_path: Path, cache: dict[str, list[str]]):
    """Save cached URLs for web sources."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def process_source(src: dict, now: datetime, cutoff: datetime,
                   seen_urls: set[str], web_cache: dict[str, list[str]],
                   reader_per_source: int = 5,
                   ) -> tuple[list[str], list[dict], list[dict], dict, str | None]:
    """Fetch and parse one source.

    Returns (log_lines, recent_entries, reader_entries, stat, error_name|None).
    recent_entries: time-filtered, used by summarize.py.
    reader_entries: top N per source regardless of age, used by reader page.
    """
    name = src["name"]
    url = src["url"]
    category = src.get("category", "Uncategorized")
    src_type = src.get("type", "rss")
    logs: list[str] = [f"Fetching: {name}..."]

    content = fetch_url(url)
    if not content:
        logs.append("  FAILED to fetch")
        return logs, [], [], {"name": name, "status": "fetch_failed", "total": 0, "recent": 0}, name

    if src_type == "web":
        entries = parse_web_page(content, name, category, url)
        if not entries:
            logs.append("  No articles found on page")
            return logs, [], [], {"name": name, "status": "parse_failed", "total": 0, "recent": 0}, None
        cached = set(web_cache.get(name, []))
        all_links = [e["link"] for e in entries]
        new_entries = [e for e in entries if e["link"] not in cached]
        for e in new_entries:
            e["parsed_date"] = now.isoformat()
            e["web_notice"] = True
        web_cache[name] = all_links
        stat = {"name": name, "status": "ok", "total": len(entries), "recent": len(new_entries)}
        logs.append(f"  Found {len(entries)} links, {len(new_entries)} new")
        reader_entries = new_entries[:reader_per_source]
        return logs, new_entries, reader_entries, stat, None
    else:
        entries = parse_feed(content, name, category)
        if not entries:
            logs.append("  No entries parsed (possibly empty or parse error)")
            return logs, [], [], {"name": name, "status": "parse_failed", "total": 0, "recent": 0}, None
        recent = []
        for e in entries:
            dt = parse_date(e["date"])
            if dt:
                e["parsed_date"] = dt.isoformat()
                if dt >= cutoff:
                    recent.append(e)
        stat = {"name": name, "status": "ok", "total": len(entries), "recent": len(recent)}
        hours = round((now - cutoff).total_seconds() / 3600)
        logs.append(f"  Found {len(entries)} total, {len(recent)} within {hours}h")
        reader_entries = entries[:reader_per_source]
        return logs, recent, reader_entries, stat, None


def main():
    parser = argparse.ArgumentParser(description="Fetch RSS feeds")
    parser.add_argument("--hours", type=int, default=24,
                        help="How many hours back to look (default: 24)")
    parser.add_argument("--sources", type=Path,
                        default=Path(__file__).parent.parent / "sources.yaml",
                        help="Path to sources.yaml")
    parser.add_argument("--output", type=Path, default=Path("/tmp/feed_entries.json"),
                        help="Output JSON path")
    parser.add_argument("--feeds-dir", type=Path, default=None,
                        help="Directory with past digest .md files for web-source dedup")
    parser.add_argument("--web-cache", type=Path, default=None,
                        help="Path to web source cache JSON (default: beside sources.yaml)")
    parser.add_argument("--workers", type=int, default=10,
                        help="Parallel fetch workers (default: 10)")
    parser.add_argument("--data-out", type=Path, default=None,
                        help="Also save flat output to this path (for persistent storage)")
    parser.add_argument("--reader-out", type=Path, default=None,
                        help="Write grouped-by-source reader JSON to this path")
    parser.add_argument("--reader-per-source", type=int, default=5,
                        help="Entries per source for reader output (default: 5)")
    args = parser.parse_args()

    sources = load_sources(args.sources)
    if not sources:
        print("No sources found in sources.yaml")
        return

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=args.hours)
    today = now.strftime("%Y-%m-%d")

    feeds_dir = args.feeds_dir or args.output.parent
    seen_urls = get_seen_urls(feeds_dir, today)

    cache_path = args.web_cache or (args.sources.parent / "web_seen.json")
    web_cache = load_web_cache(cache_path)

    all_entries: list[dict] = []
    errors: list[str] = []
    stats: list[dict] = []
    reader_sources: list[dict] = []

    # Fetch all sources in parallel, preserve source order for output
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(
            lambda src: process_source(src, now, cutoff, seen_urls, web_cache,
                                       args.reader_per_source),
            sources
        ))

    for src, (logs, recent, reader_entries, stat, err) in zip(sources, results):
        for line in logs:
            print(line)
        stats.append(stat)
        if err:
            errors.append(err)
        all_entries.extend(recent)
        if reader_entries:
            reader_sources.append({
                "name": src["name"],
                "category": src.get("category", "Uncategorized"),
                "entries": [
                    {"title": e["title"], "link": e["link"],
                     "parsed_date": e.get("parsed_date", "")}
                    for e in reader_entries
                ],
            })

    # Save updated web cache
    save_web_cache(cache_path, web_cache)

    # Sort by date (newest first)
    all_entries.sort(key=lambda x: x.get("parsed_date", ""), reverse=True)

    output = {
        "fetched_at": now.isoformat(),
        "cutoff_hours": args.hours,
        "sources_checked": len(sources),
        "entries_found": len(all_entries),
        "errors": errors,
        "stats": stats,
        "entries": all_entries,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    if args.data_out:
        args.data_out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.data_out, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

    if args.reader_out:
        reader_output = {
            "fetched_at": now.isoformat(),
            "sources": reader_sources,
        }
        args.reader_out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.reader_out, "w", encoding="utf-8") as f:
            json.dump(reader_output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*40}")
    print(f"Sources checked: {len(sources)}")
    print(f"Entries found: {len(all_entries)}")
    print(f"Errors: {errors or 'none'}")
    print(f"Output: {args.output}")


if __name__ == '__main__':
    main()
