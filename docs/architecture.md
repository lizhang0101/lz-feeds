# lz-feeds Architecture

> This document is the **refactoring contract** for the parallel agents working on this codebase.
> All agents must read this before making any changes.

---

## 1. Current State Analysis

### 1.1 Module Responsibilities

| Script | Primary Job | Secondary Jobs (overloaded) |
|---|---|---|
| `scripts/fetch_feeds.py` | Fetch RSS/Atom/web sources and filter recent entries | HTML stripping, date parsing, web page link extraction, reader JSON assembly, web-source dedup caching, snippet generation |
| `scripts/summarize.py` | Score+summarize entries via Gemini, render markdown digest | Reader JSON enrichment (completely separate mode hidden behind `--enrich-reader` flag), date formatting helpers, dedup against previous digests |
| `scripts/fetch_hotlist.py` | Fetch Zhihu hot list, render markdown | Self-contained; no shared code with the other two scripts |

### 1.2 Data Flow

```
sources.yaml
     │
     ▼
fetch_feeds.py ──────────────────────────────────────────────────────┐
  │  Inputs: sources.yaml, data/web_seen.json, past digest .md files  │
  │  Outputs:                                                           │
  │    /tmp/feed_entries.json      (summarize.py input)                │
  │    _data/latest_entries.json   (reader page data, Jekyll/_data)    │
  │    data/web_seen.json          (mutated in-place, web-source dedup)│
  └────────────────────────────────────────────────────────────────────┘
     │
     ▼
summarize.py  (mode 1: digest)
  │  Input:  /tmp/feed_entries.json
  │  Output: _digests/YYYY-MM-DD.md
  └─────────────────────────────────

summarize.py  (mode 2: reader enrichment)
  │  Input:  _data/latest_entries.json  (mutated in-place)
  │  Output: _data/latest_entries.json  (with ai_summary fields added)
  └─────────────────────────────────────────────────────────────────────

fetch_hotlist.py  (independent pipeline)
  │  Input:  Zhihu API (hardcoded URL)
  │  Output: _hotlist/zhihu.md
  └──────────────────────────────

_digests/*.md + _hotlist/*.md + _data/latest_entries.json
     │
     ▼
Jekyll site (GitHub Pages)
```

### 1.3 Identified Technical Debt

#### TD-1: `fetch_url` is duplicated verbatim in two scripts
- `fetch_feeds.py` line 26–35: generic curl wrapper with `FeedBot/1.0` user-agent
- `fetch_hotlist.py` line 21–31: essentially the same function but with a browser user-agent and extra Referer header

Both wrap `subprocess.run(["curl", ...])`. Neither shares code. Any change to retry logic, timeout, or error handling must be made twice.

#### TD-2: `summarize.py` has two unrelated modes in one script
`main()` branches on `--enrich-reader`: if present, it runs reader enrichment (completely different I/O) and returns. The two modes share only `get_api_key()` and the Gemini client setup. This violates single responsibility and makes the CLI confusing — `summarize.py --enrich-reader` is really `enrich_reader.py`.

#### TD-3: Date parsing is only in `fetch_feeds.py`
`parse_date()` (lines 38–65) is a 27-line function with 8 format strings and timezone normalization. `fetch_hotlist.py` hardcodes Beijing timezone directly. If any other script ever needs date parsing, it has nowhere to import it from.

#### TD-4: `strip_html` is only in `fetch_feeds.py`, but `fetch_hotlist.py` would need it if excerpts were ever added
Currently `excerpt` is always `""` in `fetch_hotlist.py` (line 51). The field exists in the data structure as a placeholder. When that feature is added, the author will either duplicate `strip_html` or discover there's no shared lib.

#### TD-5: `process_source()` in `fetch_feeds.py` does too much (lines 414–477)
This single function handles: type dispatch (link/web/rss), HTTP fetch, parse routing, time filtering, web-cache mutation, reader entry assembly, and logging. It returns a 5-tuple. It is hard to test, extend, or reason about any one concern in isolation.

#### TD-6: Reader JSON assembly is buried inside `fetch_feeds.py main()`
The post-processing loop at lines 531–562 (building `reader_sources`) is not encapsulated in any function. It mixes business logic (is_new threshold = 72h) with output formatting. The 72-hour hardcoded constant differs from the `--hours` CLI argument and is not documented.

#### TD-7: `fetch_hotlist.py` has hardcoded sources in a `SOURCES` list constant
Adding a new hot-list platform requires editing the script itself. There is no configuration file for hotlist sources (unlike `sources.yaml` for feeds).

#### TD-8: No tests whatsoever
The following functions contain non-trivial logic with no test coverage:
- `parse_date` — 8 formats, timezone edge cases
- `strip_html` — regex HTML removal + unescape
- `parse_feed` / `_parse_atom` / `_parse_rss` — XML parsing with namespace handling
- `BlogLinkExtractor.get_article_links` — heuristic article detection
- `render` in `summarize.py` — markdown output with multiple sections
- `parse_zhihu` — JSON parsing with missing-field handling

#### TD-9: Implicit data contract between `fetch_feeds.py` and `summarize.py`
`summarize.py` reads `/tmp/feed_entries.json` and expects fields `link`, `source`, `title`, `content`, `parsed_date`. This contract is implicit — there is no schema definition, no validation, and no documentation of what fields are required vs. optional.

#### TD-10: `data/` vs `_data/` confusion
- `data/web_seen.json` — runtime cache mutated by `fetch_feeds.py`
- `data/source_stats.json` — appears to be generated but not documented
- `_data/latest_entries.json` — Jekyll data file written by `fetch_feeds.py`

The split between `data/` (runtime/cache) and `_data/` (Jekyll) is not documented and leads to confusion about what belongs where.

---

## 2. Refactoring Goals

### 2.1 Target Module Structure

```
lz-feeds/
├── scripts/
│   ├── fetch_feeds.py          # Unchanged CLI interface; internals refactored
│   ├── summarize.py            # Digest-only; --enrich-reader removed
│   ├── enrich_reader.py        # NEW: extracted from summarize.py --enrich-reader
│   ├── fetch_hotlist.py        # Unchanged CLI interface; uses lib/http.py
│   └── lib/
│       ├── __init__.py
│       ├── http.py             # NEW: shared fetch_url with configurable headers
│       ├── parsing.py          # NEW: parse_date, strip_html, make_snippet
│       ├── models.py           # NEW: dataclasses for FeedEntry, ReaderEntry, SourceStat
│       └── feed_parser.py      # EXTRACTED: parse_feed, _parse_atom, _parse_rss, BlogLinkExtractor
├── tests/
│   ├── __init__.py
│   ├── test_parsing.py         # parse_date, strip_html, make_snippet
│   ├── test_feed_parser.py     # parse_feed (RSS + Atom fixtures)
│   ├── test_blog_extractor.py  # BlogLinkExtractor
│   └── fixtures/
│       ├── sample_rss.xml
│       ├── sample_atom.xml
│       └── sample_blog.html
├── docs/
│   └── architecture.md         # This file
└── ... (unchanged: sources.yaml, requirements.txt, _data/, etc.)
```

### 2.2 Shared Module Design (`lib/`)

#### `lib/http.py`
Single responsibility: make HTTP requests via curl subprocess.

```python
def fetch_url(url: str, headers: dict[str, str] | None = None, timeout: int = 15) -> str | None:
    """Fetch URL with curl. Returns response body or None on failure."""
```

Replaces both `fetch_url` implementations. `fetch_hotlist.py` passes its custom headers; `fetch_feeds.py` passes the FeedBot user-agent. The default headers should be the generic FeedBot ones.

#### `lib/parsing.py`
Single responsibility: text parsing utilities that have no I/O side effects.

```python
def parse_date(date_str: str) -> datetime | None: ...
def strip_html(text: str, max_chars: int = 2000) -> str: ...
def make_snippet(content: str, max_sentences: int = 3, max_chars: int = 320) -> str: ...
```

#### `lib/models.py`
Single responsibility: typed data structures shared across scripts.

```python
@dataclass
class FeedEntry:
    title: str
    link: str
    date: str | None          # raw date string from feed
    parsed_date: str | None   # ISO 8601, set after parse_date()
    content: str              # strip_html applied
    source: str
    category: str

@dataclass
class ReaderEntry:
    title: str
    link: str
    parsed_date: str
    is_new: bool
    snippet: str
    ai_summary: str = ""

@dataclass
class SourceStat:
    name: str
    status: str               # "ok" | "fetch_failed" | "parse_failed"
    total: int
    recent: int
```

Using dataclasses (or TypedDict) makes the implicit contract between scripts explicit and statically checkable.

#### `lib/feed_parser.py`
Single responsibility: parse feed XML/HTML into `FeedEntry` lists.

```python
def parse_feed(xml_text: str, source_name: str, category: str) -> list[FeedEntry]: ...
def parse_web_page(html_text: str, source_name: str, category: str, base_url: str) -> list[FeedEntry]: ...
class BlogLinkExtractor(HTMLParser): ...  # moved here from fetch_feeds.py
```

### 2.3 Per-Script Refactoring Notes

#### `fetch_feeds.py`
- Replace local `fetch_url`, `parse_date`, `strip_html`, `make_snippet` with imports from `lib/`
- Replace local `parse_feed` / `_parse_atom` / `_parse_rss` / `BlogLinkExtractor` with imports from `lib/feed_parser`
- Extract `process_source()` into smaller focused functions:
  - `_fetch_and_parse(src, web_cache) -> list[FeedEntry]` — I/O only
  - `_filter_recent(entries, cutoff) -> list[FeedEntry]` — time filter, pure
  - `_build_reader_entries(entries, now, per_source) -> list[ReaderEntry]` — pure
- Document the 72-hour `is_new` constant; consider making it a CLI arg `--reader-new-hours`
- Keep all existing CLI arguments unchanged

#### `summarize.py`
- Remove `enrich_reader()` function and the `--enrich-reader` CLI argument entirely
- Move those to `enrich_reader.py`
- Keep all other CLI arguments unchanged: `--input`, `--output`, `--model`, `--top`, `--extended`, `--digests-dir`, `--force`

#### `enrich_reader.py` (new script)
- Extract `enrich_reader()` from `summarize.py`
- CLI: `python scripts/enrich_reader.py [--reader PATH] [--model MODEL]`
- Update `daily.yml` step "Enrich reader" to call `enrich_reader.py` instead of `summarize.py --enrich-reader`

#### `fetch_hotlist.py`
- Replace local `fetch_url` with `from lib.http import fetch_url`
- Optionally: move `SOURCES` to a config section in `sources.yaml` under a `hotlists:` key — but this is lower priority and should not block other refactoring

---

## 3. Data Contracts

### 3.1 `_data/latest_entries.json` Schema

This is the Jekyll data file consumed by the reader page. Written by `fetch_feeds.py`, enriched in-place by `summarize.py --enrich-reader` (soon `enrich_reader.py`).

```jsonc
{
  "fetched_at": "ISO-8601 datetime string",  // required
  "sources": [                                // required, array
    {
      "name": "string",                       // required, display name
      "category": "string",                   // required
      "group": "blog" | "vendor" | "...",     // optional, defaults to "blog"
      "latest_date": "ISO-8601 | ''",         // required, "" if no dated entries
      "stale": true | false,                  // required, set after fetch; true if latest_date > 30 days ago
      "entries": [                            // required, array, max reader_per_source items
        {
          "title": "string",                  // required
          "link": "https://...",              // required
          "parsed_date": "ISO-8601 | ''",     // required, "" if date unknown
          "is_new": true | false,             // required; true if entry is within 72h of fetch
          "snippet": "string",               // required, may be ""
          "ai_summary": "string"             // optional; added by enrich_reader step
        }
      ]
    }
  ]
}
```

### 3.2 `feed_entries.json` Schema (internal intermediate format)

Written by `fetch_feeds.py` to `/tmp/feed_entries.json` (or `--output`). Read by `summarize.py`.

```jsonc
{
  "fetched_at": "ISO-8601 datetime string",   // required
  "cutoff_hours": 72,                          // required, integer
  "sources_checked": 30,                       // required, integer
  "entries_found": 120,                        // required, integer
  "errors": ["source name", ...],              // required, array of failed source names
  "stats": [                                   // required, one per source
    {
      "name": "string",
      "status": "ok" | "fetch_failed" | "parse_failed",
      "total": 0,
      "recent": 0
    }
  ],
  "entries": [                                 // required, sorted newest-first
    {
      "title": "string",                       // required
      "link": "https://...",                   // required
      "date": "raw date string | null",        // optional; raw value from feed
      "parsed_date": "ISO-8601 | ''",          // required after fetch; "" if unparseable
      "content": "string",                     // required, HTML-stripped, max 2000 chars
      "source": "string",                      // required, display name
      "category": "string",                    // required
      "web_notice": true                       // optional; present only for type:web new entries
    }
  ]
}
```

---

## 4. Refactoring Constraints

### CLI interfaces that MUST remain compatible

These are called directly by GitHub Actions workflows and must not change:

| Script | Called as | Must keep |
|---|---|---|
| `fetch_feeds.py` | `python scripts/fetch_feeds.py --hours 72 --web-cache data/web_seen.json --reader-out _data/latest_entries.json` | All flags listed |
| `summarize.py` | `python scripts/summarize.py` | Zero-arg invocation must still work |
| `fetch_hotlist.py` | `python scripts/fetch_hotlist.py` | Zero-arg invocation must still work |

The `summarize.py --enrich-reader` flag is called in `daily.yml` at the "Enrich reader" step. **This step must be updated in the same PR as the extraction of `enrich_reader.py`** to avoid breaking the pipeline.

### Output paths that MUST remain stable

| Path | Written by | Read by |
|---|---|---|
| `_data/latest_entries.json` | `fetch_feeds.py --reader-out` | Jekyll site, `enrich_reader.py` |
| `_digests/YYYY-MM-DD.md` | `summarize.py` | Jekyll site, `summarize.py` (prev_featured dedup) |
| `_hotlist/zhihu.md` | `fetch_hotlist.py` | Jekyll site |
| `data/web_seen.json` | `fetch_feeds.py --web-cache` | `fetch_feeds.py` (next run) |

### Import compatibility
`lib/` will be a package inside `scripts/`. Scripts import it as:
```python
from lib.http import fetch_url
from lib.parsing import parse_date, strip_html
```
This works when scripts are run from the repo root as `python scripts/fetch_feeds.py` because Python adds the script's directory to `sys.path`. **Verify this holds in the GitHub Actions environment** before merging — add a smoke test step or import guard if needed.

---

## 5. Testing Strategy

### Priority order (highest value / lowest effort first)

1. **`lib/parsing.py`** — pure functions, no I/O, easiest to test
   - `parse_date`: cover RFC 2822, ISO 8601 with/without timezone, ISO with milliseconds, date-only, empty string, invalid input, timezone normalization to UTC
   - `strip_html`: tags, entities, whitespace normalization, truncation at 2000 chars
   - `make_snippet`: sentence splitting, max_chars truncation, empty input

2. **`lib/feed_parser.py`** — needs XML/HTML fixtures, medium effort
   - `parse_feed` with a real RSS 2.0 fixture
   - `parse_feed` with a real Atom 1.0 fixture
   - `parse_feed` with namespaced Atom (common in practice)
   - `BlogLinkExtractor.get_article_links` with a minimal HTML fixture

3. **`summarize.py render()`** — pure markdown renderer, no I/O
   - Verify section headings, frontmatter keys, table row format
   - Verify `prev_featured` correctly excludes entries from top/extended

4. **`fetch_feeds.py process_source()` (after extraction into pure sub-functions)**
   - `_filter_recent`: cutoff logic, edge cases (exactly at cutoff, no parsed_date)
   - `_build_reader_entries`: is_new threshold, stale detection

### Recommended framework and structure

```
pytest>=8.0          # add to requirements.txt or requirements-dev.txt
```

```
tests/
├── __init__.py
├── conftest.py              # shared fixtures (sample XML strings, etc.)
├── test_parsing.py
├── test_feed_parser.py
├── test_blog_extractor.py
├── test_render.py
└── fixtures/
    ├── sample_rss.xml       # minimal valid RSS 2.0 with 2-3 items
    ├── sample_atom.xml      # minimal valid Atom with namespace
    └── sample_blog.html     # simple page with nav, article links, footer
```

Run locally with `pytest tests/` from the repo root. Add a `test.yml` workflow later (not required in this refactoring sprint).

---

## 6. Agent Assignment

### Agent A — Script Refactoring

**Scope:** All changes inside `scripts/` and `tests/`. Must not touch `_layouts/`, `_includes/`, `assets/`, Jekyll config, or workflow files except for the one required workflow change below.

**Deliverables:**
1. Create `scripts/lib/__init__.py`, `scripts/lib/http.py`, `scripts/lib/parsing.py`, `scripts/lib/models.py`, `scripts/lib/feed_parser.py`
2. Refactor `fetch_feeds.py` to import from `lib/` (no behavior change, CLI unchanged)
3. Extract `enrich_reader.py` from `summarize.py`; remove `--enrich-reader` from `summarize.py`
4. Refactor `fetch_hotlist.py` to import `fetch_url` from `lib/http.py`
5. Update `.github/workflows/daily.yml` step "Enrich reader with AI summaries" to call `enrich_reader.py` instead of `summarize.py --enrich-reader`
6. Create `tests/` with coverage for `lib/parsing.py` (minimum), `lib/feed_parser.py` (medium priority)

**Must not break:**
- `python scripts/fetch_feeds.py --hours 72 --web-cache data/web_seen.json --reader-out _data/latest_entries.json`
- `python scripts/summarize.py`
- `python scripts/fetch_hotlist.py`

**Validation:** Run `pytest tests/` locally. Do a dry-run of `python scripts/fetch_feeds.py --help` and `python scripts/summarize.py --help` to confirm CLI is unchanged.

### Agent C — Documentation

**Scope:** `docs/` only. No changes to scripts or workflows.

**Deliverables:**
1. `docs/sources.md` — guide for adding/removing feed sources (sources.yaml field reference, type options, group field meaning)
2. `docs/operations.md` — how the daily pipeline runs (workflow schedule, manual trigger, what each step does, how to debug failures)
3. Update `README.md` if it references outdated paths or missing features (e.g., the reader page, hotlist feature)

**Must not break:** nothing — documentation only.

**Dependency on Agent A:** Agent C should write docs that describe the post-refactoring structure. If Agent A is not done yet, write docs based on this architecture document and note "pending refactor" where applicable.
