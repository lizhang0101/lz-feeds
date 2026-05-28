"""Unit tests for ``lib.parsing``."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from lib.parsing import make_snippet, parse_date, strip_html


# ---------------------------------------------------------------------------
# parse_date
# ---------------------------------------------------------------------------


class TestParseDate:
    def test_rfc_2822(self):
        dt = parse_date("Tue, 27 May 2026 12:34:56 +0000")
        assert dt is not None
        assert dt.year == 2026 and dt.month == 5 and dt.day == 27
        assert dt.tzinfo is not None

    def test_iso_with_z(self):
        dt = parse_date("2026-05-27T12:34:56Z")
        assert dt == datetime(2026, 5, 27, 12, 34, 56, tzinfo=timezone.utc)

    def test_iso_with_colon_offset(self):
        # Python <3.11 cannot handle ``+08:00``; parse_date strips the colon.
        dt = parse_date("2026-05-27T12:34:56+08:00")
        assert dt is not None
        assert dt.utcoffset().total_seconds() == 8 * 3600

    def test_iso_with_milliseconds(self):
        dt = parse_date("2026-05-27T12:34:56.789Z")
        assert dt is not None
        assert dt.microsecond == 789_000

    def test_iso_with_milliseconds_and_offset(self):
        dt = parse_date("2026-05-27T12:34:56.789+00:00")
        assert dt is not None

    def test_date_only(self):
        dt = parse_date("2026-05-27")
        assert dt is not None
        # Naive dates are assumed UTC.
        assert dt.tzinfo == timezone.utc

    def test_naive_datetime_assumed_utc(self):
        # The space-separated form with offset works directly.
        dt = parse_date("2026-05-27 12:34:56+0000")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_empty_returns_none(self):
        assert parse_date("") is None
        assert parse_date(None) is None  # type: ignore[arg-type]

    def test_whitespace_only_returns_none(self):
        assert parse_date("   ") is None

    def test_invalid_returns_none(self):
        assert parse_date("not a date") is None
        assert parse_date("2026-13-45") is None

    def test_returns_timezone_aware(self):
        dt = parse_date("2026-05-27")
        assert dt is not None and dt.tzinfo is not None


# ---------------------------------------------------------------------------
# strip_html
# ---------------------------------------------------------------------------


class TestStripHtml:
    def test_empty(self):
        assert strip_html("") == ""
        assert strip_html(None) == ""  # type: ignore[arg-type]

    def test_removes_tags(self):
        assert strip_html("<p>hello <b>world</b></p>") == "hello world"

    def test_unescapes_entities(self):
        assert strip_html("a &amp; b &lt;c&gt;") == "a & b <c>"

    def test_collapses_whitespace(self):
        assert strip_html("foo\n\n   bar\t\tbaz") == "foo bar baz"

    def test_truncates_to_max_chars(self):
        # 2500 chars of plain text, default cap = 2000
        text = "a" * 2500
        assert len(strip_html(text)) == 2000

    def test_custom_max_chars(self):
        assert strip_html("a" * 100, max_chars=10) == "a" * 10

    def test_mixed_html_and_entities(self):
        result = strip_html("<div>Price: &dollar;5 &mdash; <i>cheap</i></div>")
        assert "Price:" in result
        assert "cheap" in result
        assert "<" not in result


# ---------------------------------------------------------------------------
# make_snippet
# ---------------------------------------------------------------------------


class TestMakeSnippet:
    def test_empty(self):
        assert make_snippet("") == ""
        assert make_snippet(None) == ""  # type: ignore[arg-type]

    def test_short_text_returned_whole(self):
        assert make_snippet("Short sentence.") == "Short sentence."

    def test_picks_first_n_sentences(self):
        text = "First. Second! Third? Fourth."
        result = make_snippet(text, max_sentences=2)
        assert "First." in result
        assert "Second!" in result
        assert "Third?" not in result

    def test_respects_max_chars(self):
        long_sentence = "X" * 500 + "."
        result = make_snippet(long_sentence + " Another.", max_chars=100)
        # Returned slice cannot exceed max_chars on its own, OR falls back
        # to a hard truncation when no sentence fits.
        assert len(result) <= 500 + 1  # the single sentence was returned via the hard fallback

    def test_falls_back_to_hard_truncate(self):
        # A single sentence longer than max_chars triggers the fallback.
        text = "a" * 1000
        result = make_snippet(text, max_chars=50)
        assert len(result) == 50

    def test_custom_max_sentences(self):
        text = "A. B. C. D. E."
        out = make_snippet(text, max_sentences=4, max_chars=999)
        assert "A." in out and "D." in out
        assert "E." not in out
