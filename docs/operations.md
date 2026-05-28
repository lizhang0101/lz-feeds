# Operations

How the lz-feeds pipeline runs in production and how to work on it locally.

## Workflows

Two scheduled GitHub Actions workflows drive the site. Both also accept
`workflow_dispatch` for manual runs.

### `.github/workflows/daily.yml` — Daily Digest

- **Schedule:** `17 0 * * *` UTC = **08:17 Beijing time**, once per day.
- **Trigger:** schedule, or manual via Actions tab.
- **Secret required:** `GEMINI_API_KEY`.
- **Steps:**
  1. **Checkout** the repo.
  2. **Setup Python 3.12**.
  3. **Install dependencies** — `pip install -r requirements.txt`.
  4. **Fetch feeds** — runs
     `python scripts/fetch_feeds.py --hours 72 --web-cache data/web_seen.json --reader-out _data/latest_entries.json`.
     Produces `/tmp/feed_entries.json` (digest input) and overwrites
     `_data/latest_entries.json` (reader page data).
  5. **Summarize** — runs `python scripts/summarize.py`. Uses Gemini to
     score and summarize entries, writes `_digests/YYYY-MM-DD.md`.
  6. **Enrich reader with AI summaries** — runs
     `python scripts/enrich_reader.py _data/latest_entries.json`
     (post-refactor; previously `summarize.py --enrich-reader`). Mutates
     `_data/latest_entries.json` in place, adding `ai_summary` per entry.
  7. **Commit & push** — stages `_digests/`, `_data/`, `data/` and commits
     under the `github-actions[bot]` identity, then pushes to `main`.
  8. **Deploy Pages** — triggers `pages.yml` via `gh workflow run`.

### `.github/workflows/hotlist.yml` — Hot List

- **Schedule:** `0 */2 * * *` — every 2 hours.
- **Trigger:** schedule or manual.
- **Secrets:** none.
- **Steps:**
  1. Checkout, setup Python 3.12.
  2. **Fetch hot lists** — `python scripts/fetch_hotlist.py`. Writes
     `_hotlist/zhihu.md`.
  3. **Commit & push** the `_hotlist/` changes.
  4. **Deploy Pages** via `gh workflow run pages.yml`.

`pages.yml` (not detailed here) builds the Jekyll site and deploys to GitHub
Pages.

## Required secrets

Set in **Settings → Secrets and variables → Actions** of the GitHub repo:

| Secret           | Used by                              | Notes                                                                                   |
|------------------|--------------------------------------|-----------------------------------------------------------------------------------------|
| `GEMINI_API_KEY` | `summarize.py`, `enrich_reader.py`   | Google Gemini API key. Free tier from <https://aistudio.google.com> is enough. |

`GITHUB_TOKEN` is provided automatically by GitHub Actions; no setup needed.

## Manually triggering a workflow

From the GitHub UI:

1. Open the **Actions** tab.
2. Pick **Daily Digest** or **Hot List** from the left sidebar.
3. Click **Run workflow** → choose `main` → **Run workflow**.

From the CLI (requires `gh` authenticated against the repo):

```bash
gh workflow run daily.yml
gh workflow run hotlist.yml
```

## Debugging a failed run

1. Open the failed run in the **Actions** tab. Each step expands to its full
   stdout/stderr log.
2. Common failure modes and where to look:
   - **`Fetch feeds` step succeeds but a source shows `status: fetch_failed`** —
     transient HTTP / DNS issue. Check the step log for the source name; the
     script logs each failure but continues. No action needed unless it
     persists across multiple days.
   - **`Summarize` / `Enrich reader` step fails with auth/quota error** —
     verify `GEMINI_API_KEY` secret is set and has quota. Re-run the
     workflow.
   - **`Commit & push` step fails with "nothing to commit"** — not a failure;
     the `git diff --cached --quiet || git commit ...` line is designed to
     skip empty commits.
   - **`Deploy Pages` step fails** — open `pages.yml` runs separately to see
     the Jekyll build log.
3. For deeper investigation, re-run locally with the same args (see below) to
   reproduce.

Workflow run logs are retained for 90 days by default.

## Local development

All scripts run from the repo root. Python 3.12 is recommended to match CI.

```bash
pip install -r requirements.txt
```

### Fetch feeds and update reader data

```bash
python scripts/fetch_feeds.py \
  --hours 72 \
  --web-cache data/web_seen.json \
  --reader-out _data/latest_entries.json
```

Useful flags (see `--help` for the full list):

- `--hours N` — look-back window in hours (default 24; CI uses 72).
- `--sources PATH` — override `sources.yaml` path.
- `--output PATH` — intermediate JSON for `summarize.py` (default
  `/tmp/feed_entries.json`).
- `--reader-out PATH` — grouped-by-source reader JSON.
- `--reader-per-source N` — entries per source kept for the reader (default 5).
- `--workers N` — parallel fetch workers (default 10).

### Generate the daily digest

```bash
GEMINI_API_KEY=your_key python scripts/summarize.py
```

Reads `/tmp/feed_entries.json`, writes `_digests/YYYY-MM-DD.md`. Useful flags:
`--input`, `--output`, `--model`, `--top`, `--extended`, `--digests-dir`,
`--force` (overwrite an existing digest for today).

### Enrich the reader with AI summaries

Post-refactor, this is a separate script (see `docs/architecture.md` §2.3):

```bash
GEMINI_API_KEY=your_key python scripts/enrich_reader.py _data/latest_entries.json
```

It mutates `_data/latest_entries.json` in place. Entries that already have a
non-empty `ai_summary` are skipped, so re-running is cheap.

### Fetch the hot list

```bash
python scripts/fetch_hotlist.py
```

Writes `_hotlist/zhihu.md`. No flags; sources are currently hardcoded in the
script (see `docs/architecture.md` TD-7).

### Preview the Jekyll site

```bash
bundle install
bundle exec jekyll serve
```

Site is then available at <http://127.0.0.1:4000/lz-feeds/>.

## Data locations cheat-sheet

| Path                          | Written by             | Purpose                                  |
|-------------------------------|------------------------|------------------------------------------|
| `_data/latest_entries.json`   | `fetch_feeds.py`, `enrich_reader.py` | Reader page data (Jekyll `_data`) |
| `_digests/YYYY-MM-DD.md`      | `summarize.py`         | Daily digest collection                  |
| `_hotlist/zhihu.md`           | `fetch_hotlist.py`     | Hot-list snapshot                        |
| `data/web_seen.json`          | `fetch_feeds.py`       | Dedup cache for `type: web` sources      |
| `data/source_stats.json`      | `fetch_feeds.py`       | Per-source fetch history                 |
| `/tmp/feed_entries.json`      | `fetch_feeds.py`       | Intermediate input to `summarize.py`     |

See `docs/architecture.md` §3 for full schemas of the JSON files.
