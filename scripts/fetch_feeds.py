#!/usr/bin/env python3
"""Fetch RSS/Atom/web sources and emit recent entries plus reader JSON.

Usage:
    python fetch_feeds.py [--hours N] [--sources PATH] [--output PATH]
                          [--reader-out PATH] [--web-cache PATH]
                          [--reader-per-source N] [--reader-new-hours N]
                          [--workers N] [--data-out PATH]

Defaults:
    --hours 24
    --sources ../sources.yaml
    --output /tmp/feed_entries.json
    --reader-new-hours 72
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

# ``lib`` is a sibling package; Python adds ``scripts/`` to sys.path
# automatically when ``python scripts/fetch_feeds.py`` is run from the
# repo root, but make it explicit so direct imports work from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.feed_parser import parse_feed, parse_web_page  # noqa: E402
from lib.http import fetch_url  # noqa: E402
from lib.parsing import make_snippet, parse_date  # noqa: E402


READER_NEW_HOURS_DEFAULT = 72  # entries newer than this are flagged ``is_new``
READER_STALE_DAYS = 30          # sources whose newest entry is older are ``stale``


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def load_sources(path: Path) -> list[dict]:
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("sources", []) or []


def load_web_cache(cache_path: Path) -> dict[str, list[str]]:
    if cache_path.exists():
        with open(cache_path) as f:
            return json.load(f)
    return {}


def save_web_cache(cache_path: Path, cache: dict[str, list[str]]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Per-source processing (extracted from the old ``process_source``)
# ---------------------------------------------------------------------------


def _filter_recent(entries: list[dict], cutoff: datetime) -> list[dict]:
    """Annotate ``parsed_date`` and keep entries dated at/after ``cutoff``.

    Pure: mutates the entries to add ``parsed_date`` but returns a new
    filtered list.
    """
    recent: list[dict] = []
    for entry in entries:
        dt = parse_date(entry.get("date"))
        if dt is None:
            continue
        entry["parsed_date"] = dt.isoformat()
        if dt >= cutoff:
            recent.append(entry)
    return recent


def _fetch_and_parse(
    src: dict,
    now: datetime,
    web_cache: dict[str, list[str]],
) -> tuple[list[str], list[dict], list[dict], dict, str | None]:
    """Perform I/O and parsing for a single source.

    Returns ``(logs, recent_or_new_entries, all_parsed_entries, stat, error)``.

    ``recent_or_new_entries`` is what should feed into the digest
    pipeline (time-filtered for RSS, newly-seen for web). The caller
    further filters / shapes ``all_parsed_entries`` for the reader page.
    """
    name = src["name"]
    url = src["url"]
    category = src.get("category", "Uncategorized")
    src_type = src.get("type", "rss")
    logs = [f"Fetching: {name}..."]

    if src_type == "link":
        logs.append("  Static link (no fetch)")
        reader_entry = {
            "title": "访问博客",
            "link": url,
            "parsed_date": "",
            "is_new": False,
            "_link_passthrough": True,
        }
        return (
            logs,
            [],
            [reader_entry],
            {"name": name, "status": "ok", "total": 0, "recent": 0},
            None,
        )

    body = fetch_url(url)
    if not body:
        logs.append("  FAILED to fetch")
        return (
            logs,
            [],
            [],
            {"name": name, "status": "fetch_failed", "total": 0, "recent": 0},
            name,
        )

    if src_type == "web":
        entries = parse_web_page(body, name, category, url)
        if not entries:
            logs.append("  No articles found on page")
            return (
                logs,
                [],
                [],
                {"name": name, "status": "parse_failed", "total": 0, "recent": 0},
                None,
            )
        cached = set(web_cache.get(name, []))
        all_links = [e["link"] for e in entries]
        new_entries = [e for e in entries if e["link"] not in cached]
        for entry in new_entries:
            entry["parsed_date"] = now.isoformat()
            entry["web_notice"] = True
        web_cache[name] = all_links
        stat = {
            "name": name,
            "status": "ok",
            "total": len(entries),
            "recent": len(new_entries),
        }
        logs.append(f"  Found {len(entries)} links, {len(new_entries)} new")
        return logs, new_entries, entries, stat, None

    # Default: RSS/Atom feed.
    entries = parse_feed(body, name, category)
    if not entries:
        logs.append("  No entries parsed (possibly empty or parse error)")
        return (
            logs,
            [],
            [],
            {"name": name, "status": "parse_failed", "total": 0, "recent": 0},
            None,
        )
    return logs, entries, entries, {
        "name": name,
        "status": "ok",
        "total": len(entries),
        "recent": 0,
    }, None


def _build_reader_entries(
    src_entries: list[dict],
    now: datetime,
    per_source: int,
    new_cutoff: datetime,
) -> list[dict]:
    """Shape per-source entries for the reader page.

    Pure: takes parsed entry dicts and returns the minimal record set
    consumed by Jekyll.
    """
    out: list[dict] = []
    for entry in src_entries[:per_source]:
        if entry.get("_link_passthrough"):
            out.append(
                {
                    "title": entry["title"],
                    "link": entry["link"],
                    "parsed_date": entry.get("parsed_date", ""),
                    "is_new": False,
                    "snippet": "",
                }
            )
            continue

        parsed = entry.get("parsed_date", "")
        dt = parse_date(entry.get("date")) if entry.get("date") else None
        is_new = bool(dt and dt >= new_cutoff)
        # Web sources stamp parsed_date with ``now`` and set
        # ``web_notice``; treat those as new too.
        if entry.get("web_notice"):
            is_new = True
        out.append(
            {
                "title": entry["title"],
                "link": entry["link"],
                "parsed_date": parsed,
                "is_new": is_new,
                "snippet": make_snippet(entry.get("content", "")),
            }
        )
    return out


def process_source(
    src: dict,
    now: datetime,
    cutoff: datetime,
    web_cache: dict[str, list[str]],
    reader_per_source: int = 5,
    reader_new_cutoff: datetime | None = None,
) -> tuple[list[str], list[dict], list[dict], dict, str | None]:
    """Fetch + parse + filter one source.

    Backwards-compatible wrapper that orchestrates ``_fetch_and_parse``,
    ``_filter_recent`` and ``_build_reader_entries``.
    """
    logs, raw_for_digest, all_parsed, stat, err = _fetch_and_parse(src, now, web_cache)
    if err or stat["status"] != "ok":
        return logs, raw_for_digest, [], stat, err

    src_type = src.get("type", "rss")
    if src_type == "link":
        # ``raw_for_digest`` is []. ``all_parsed`` already holds the
        # synthetic reader entry; drop the private flag before exposing.
        reader_entries = [
            {k: v for k, v in e.items() if not k.startswith("_")}
            for e in all_parsed
        ]
        return logs, [], reader_entries, stat, None

    if src_type == "web":
        # Already filtered to new entries.
        recent = raw_for_digest
        reader_entries = _build_reader_entries(
            all_parsed, now, reader_per_source, reader_new_cutoff or cutoff
        )
        return logs, recent, reader_entries, stat, None

    # RSS/Atom: filter by cutoff for digest, keep top-N for reader.
    recent = _filter_recent(all_parsed, cutoff)
    stat["recent"] = len(recent)
    hours = round((now - cutoff).total_seconds() / 3600)
    logs.append(f"  Found {len(all_parsed)} total, {len(recent)} within {hours}h")
    reader_entries = _build_reader_entries(
        all_parsed, now, reader_per_source, reader_new_cutoff or cutoff
    )
    return logs, recent, reader_entries, stat, None


# ---------------------------------------------------------------------------
# Reader output assembly
# ---------------------------------------------------------------------------


def _assemble_reader_output(
    sources: list[dict],
    per_source_entries: list[list[dict]],
    now: datetime,
) -> dict:
    """Build the final ``_data/latest_entries.json`` payload."""
    reader_sources: list[dict] = []
    for src, entries in zip(sources, per_source_entries):
        if not entries:
            continue
        latest_date = max(
            (e["parsed_date"] for e in entries if e["parsed_date"]),
            default="",
        )
        reader_sources.append(
            {
                "name": src["name"],
                "category": src.get("category", "Uncategorized"),
                "group": src.get("group", "blog"),
                "latest_date": latest_date,
                "entries": entries,
            }
        )
    reader_sources.sort(key=lambda s: s["latest_date"], reverse=True)
    stale_cutoff = (now - timedelta(days=READER_STALE_DAYS)).isoformat()
    for src in reader_sources:
        src["stale"] = not src["latest_date"] or src["latest_date"] < stale_cutoff
    beijing = now.astimezone(timezone(timedelta(hours=8)))
    return {
        "fetched_at": now.isoformat(),
        "fetched_at_beijing": beijing.strftime("%Y-%m-%d %H:%M"),
        "sources": reader_sources,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch RSS feeds")
    parser.add_argument("--hours", type=int, default=24,
                        help="How many hours back to look (default: 24)")
    parser.add_argument("--sources", type=Path,
                        default=Path(__file__).parent.parent / "sources.yaml",
                        help="Path to sources.yaml")
    parser.add_argument("--output", type=Path, default=Path("/tmp/feed_entries.json"),
                        help="Output JSON path")
    parser.add_argument("--feeds-dir", type=Path, default=None,
                        help="Directory with past digest .md files (reserved)")
    parser.add_argument("--web-cache", type=Path, default=None,
                        help="Path to web source cache JSON (default: beside sources.yaml)")
    parser.add_argument("--workers", type=int, default=10,
                        help="Parallel fetch workers (default: 10)")
    parser.add_argument("--data-out", type=Path, default=None,
                        help="Also save flat output to this path")
    parser.add_argument("--reader-out", type=Path, default=None,
                        help="Write grouped-by-source reader JSON to this path")
    parser.add_argument("--reader-per-source", type=int, default=5,
                        help="Entries per source for reader output (default: 5)")
    parser.add_argument("--reader-new-hours", type=int, default=READER_NEW_HOURS_DEFAULT,
                        help=f"Entries newer than N hours are flagged is_new "
                             f"(default: {READER_NEW_HOURS_DEFAULT})")
    args = parser.parse_args()

    sources = load_sources(args.sources)
    if not sources:
        print("No sources found in sources.yaml")
        return

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=args.hours)
    reader_new_cutoff = now - timedelta(hours=args.reader_new_hours)

    cache_path = args.web_cache or (args.sources.parent / "web_seen.json")
    web_cache = load_web_cache(cache_path)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(
            lambda src: process_source(
                src, now, cutoff, web_cache,
                args.reader_per_source, reader_new_cutoff,
            ),
            sources,
        ))

    all_entries: list[dict] = []
    errors: list[str] = []
    stats: list[dict] = []
    per_source_reader: list[list[dict]] = []

    for logs, recent, reader_entries, stat, err in results:
        for line in logs:
            print(line)
        stats.append(stat)
        if err:
            errors.append(err)
        all_entries.extend(recent)
        per_source_reader.append(reader_entries)

    save_web_cache(cache_path, web_cache)

    all_entries.sort(key=lambda x: x.get("parsed_date", ""), reverse=True)

    # Strip private fields before writing.
    for entry in all_entries:
        entry.pop("_link_passthrough", None)

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
        reader_output = _assemble_reader_output(sources, per_source_reader, now)
        args.reader_out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.reader_out, "w", encoding="utf-8") as f:
            json.dump(reader_output, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*40}")
    print(f"Sources checked: {len(sources)}")
    print(f"Entries found: {len(all_entries)}")
    print(f"Errors: {errors or 'none'}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
