"""Unit tests for ``lib.feed_parser``."""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.feed_parser import BlogLinkExtractor, parse_feed, parse_web_page


FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# parse_feed — RSS
# ---------------------------------------------------------------------------


class TestParseRss:
    def setup_method(self):
        self.entries = parse_feed(_load("sample_rss.xml"), "Sample Blog", "Tech")

    def test_finds_all_items(self):
        assert len(self.entries) == 3

    def test_required_fields_present(self):
        for entry in self.entries:
            assert set(entry.keys()) >= {
                "title", "link", "date", "content", "source", "category"
            }

    def test_titles(self):
        titles = [e["title"] for e in self.entries]
        assert titles == ["First Post", "Second Post", "Post With dc:date"]

    def test_links(self):
        assert self.entries[0]["link"] == "https://example.com/posts/1"

    def test_strips_html_from_description(self):
        # The <p> and <b> tags must be removed; entities unescaped.
        assert self.entries[0]["content"] == "This is the first post ."

    def test_prefers_content_encoded_over_description(self):
        assert "Richer content" in self.entries[1]["content"]
        assert "Fallback description" not in self.entries[1]["content"]

    def test_source_and_category_propagated(self):
        for entry in self.entries:
            assert entry["source"] == "Sample Blog"
            assert entry["category"] == "Tech"

    def test_pubdate_preserved_raw(self):
        assert self.entries[0]["date"] == "Tue, 27 May 2026 12:34:56 +0000"


# ---------------------------------------------------------------------------
# parse_feed — Atom
# ---------------------------------------------------------------------------


class TestParseAtom:
    def setup_method(self):
        self.entries = parse_feed(_load("sample_atom.xml"), "Atom Source", "Misc")

    def test_finds_all_entries(self):
        assert len(self.entries) == 2

    def test_alternate_link_preferred(self):
        # The second entry has both rel=self and rel=alternate.
        assert self.entries[1]["link"] == "https://example.org/atom/2"

    def test_published_preferred_over_updated(self):
        assert self.entries[0]["date"] == "2026-05-27T11:00:00Z"

    def test_falls_back_to_updated_when_no_published(self):
        assert self.entries[1]["date"] == "2026-05-26T10:00:00Z"

    def test_content_or_summary_extracted(self):
        assert "Atom summary" in self.entries[0]["content"]
        assert "Atom content body" in self.entries[1]["content"]


# ---------------------------------------------------------------------------
# parse_feed — degenerate inputs
# ---------------------------------------------------------------------------


class TestParseFeedDegenerate:
    def test_invalid_xml_returns_empty(self):
        assert parse_feed("not xml at all", "X", "Y") == []

    def test_empty_string_returns_empty(self):
        assert parse_feed("", "X", "Y") == []

    def test_unknown_root_returns_empty(self):
        xml = "<?xml version='1.0'?><html><body/></html>"
        assert parse_feed(xml, "X", "Y") == []


# ---------------------------------------------------------------------------
# BlogLinkExtractor
# ---------------------------------------------------------------------------


class TestBlogLinkExtractor:
    def test_extracts_article_links(self):
        entries = parse_web_page(
            _load("sample_blog.html"),
            "Sample Blog",
            "Tech",
            "https://example.com",
        )
        links = {e["link"] for e in entries}
        assert "https://example.com/posts/first-real-article" in links
        assert "https://example.com/posts/second-deep-dive" in links
        assert "https://example.com/blog/2026/some-year-post" in links

    def test_skips_nav_and_footer(self):
        entries = parse_web_page(
            _load("sample_blog.html"),
            "Sample Blog",
            "Tech",
            "https://example.com",
        )
        for entry in entries:
            assert "/about" not in entry["link"]
            assert "/contact" not in entry["link"]
            assert "/footer-link" not in entry["link"]

    def test_skips_excluded_patterns(self):
        entries = parse_web_page(
            _load("sample_blog.html"),
            "Sample Blog",
            "Tech",
            "https://example.com",
        )
        for entry in entries:
            assert not entry["link"].endswith(".png")
            assert "/tag/" not in entry["link"]
            assert "/feed" not in entry["link"]

    def test_entries_have_required_fields(self):
        entries = parse_web_page(
            _load("sample_blog.html"),
            "Sample Blog",
            "Tech",
            "https://example.com",
        )
        for entry in entries:
            assert entry["source"] == "Sample Blog"
            assert entry["category"] == "Tech"
            assert entry["date"] is None
            assert entry["content"] == ""

    def test_extractor_max_entries(self):
        extractor = BlogLinkExtractor("https://example.com")
        extractor.feed(_load("sample_blog.html"))
        assert len(extractor.get_article_links(max_entries=2)) <= 2
