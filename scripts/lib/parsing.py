"""Pure text-parsing helpers shared across scripts.

No I/O, no side effects — everything in this module is safe to unit test
without fixtures or network access.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone


_DATE_FORMATS: tuple[str, ...] = (
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S %Z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%d",
)


def parse_date(date_str: str | None) -> datetime | None:
    """Parse a feed date string into a timezone-aware ``datetime``.

    Tries RFC 2822 and several ISO 8601 variants. Naive results are
    assumed UTC. Returns ``None`` if no format matches.
    """
    if not date_str:
        return None
    date_str = date_str.strip()
    if not date_str:
        return None

    # Some ISO timestamps include a colon in the timezone offset
    # (e.g. ``+08:00``), which ``%z`` cannot parse on older Pythons.
    date_str_fixed = re.sub(r"(\d{2}):(\d{2})$", r"\1\2", date_str)

    for candidate in (date_str, date_str_fixed):
        for fmt in _DATE_FORMATS:
            try:
                dt = datetime.strptime(candidate, fmt)
            except ValueError:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
    return None


def strip_html(text: str | None, max_chars: int = 2000) -> str:
    """Remove HTML tags, unescape entities, normalise whitespace, truncate."""
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_chars]


def make_snippet(content: str | None, max_sentences: int = 3, max_chars: int = 320) -> str:
    """Take the first few sentences from ``content``.

    Falls back to a hard char-truncation if no sentence boundary fits
    under ``max_chars``.
    """
    if not content:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", content.strip())
    result = ""
    for sentence in sentences[:max_sentences]:
        candidate = (result + " " + sentence).strip()
        if len(candidate) > max_chars:
            break
        result = candidate
    return result or content[:max_chars]
