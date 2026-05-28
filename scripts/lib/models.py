"""Typed data structures shared by the fetch and summarize scripts.

These dataclasses document the implicit JSON contract between
``fetch_feeds.py`` (writer) and ``summarize.py`` / ``enrich_reader.py``
(readers). They are intentionally permissive — scripts still pass plain
``dict`` payloads — but the dataclasses serve as a single source of
truth for field names and types, and are referenced by the tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class FeedEntry:
    """One entry from an RSS/Atom feed (or a web-page link)."""

    title: str
    link: str
    source: str
    category: str
    date: str | None = None             # raw date string from the feed
    parsed_date: str | None = None      # ISO 8601 after parse_date()
    content: str = ""                   # HTML-stripped, max 2000 chars
    web_notice: bool = False            # True for newly-seen ``type:web`` links

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["web_notice"]:
            data.pop("web_notice")
        return data


@dataclass
class ReaderEntry:
    """One entry shown on the Jekyll reader page (``_data/latest_entries.json``)."""

    title: str
    link: str
    parsed_date: str = ""
    is_new: bool = False
    snippet: str = ""
    ai_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceStat:
    """Per-source fetch outcome reported in ``feed_entries.json`` stats."""

    name: str
    status: str = "ok"  # "ok" | "fetch_failed" | "parse_failed"
    total: int = 0
    recent: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReaderSource:
    """One source bucket on the reader page."""

    name: str
    category: str
    group: str = "blog"
    latest_date: str = ""
    stale: bool = False
    entries: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
