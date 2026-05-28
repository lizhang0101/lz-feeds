# Managing Feed Sources

Sources are defined in [`sources.yaml`](../sources.yaml) at the repo root. This
file is the single source of truth for which feeds the pipeline polls.

## File format

Each entry under `sources:` is a YAML mapping with the following fields:

| Field      | Required | Description |
|------------|----------|-------------|
| `name`     | yes      | Display name shown on the reader page and in digests. Must be unique. |
| `url`      | yes      | Feed URL (`rss`/`web`) or destination URL (`link`). |
| `category` | yes      | Free-form grouping label (e.g. `AI`, `Programming`). Currently informational; it is preserved in the intermediate JSON but the reader page groups primarily by `group`. |
| `type`     | yes      | One of `rss`, `web`, `link`, `hotlist`. See below. |
| `language` | no       | `en` or `zh`. Helps the Gemini summarizer pick output style. Defaults to `en`. |
| `group`    | no       | `blog` (default) or `vendor`. Controls reader-page section. |

Example minimal entry:

```yaml
- name: Simon Willison
  url: https://simonwillison.net/atom/everything/
  category: AI
  type: rss
  language: en
```

## The four `type` values

### `type: rss`
Standard RSS 2.0 or Atom 1.0 feed. This is the preferred type — use it whenever
the source provides a real feed.

```yaml
- name: Armin Ronacher (lucumr)
  url: https://lucumr.pocoo.org/feed.atom
  category: Programming
  type: rss
  language: en
```

### `type: web`
HTML page that lists articles but has no feed. `fetch_feeds.py` runs the
`BlogLinkExtractor` heuristic to pull article links from the page. New URLs are
remembered in `data/web_seen.json` so the same entry is not reported on every
run. Use this only when no RSS exists and the page has a stable list layout.

```yaml
- name: Matt Shumer
  url: https://shumer.dev/blog
  category: AI
  type: web
  language: en
```

### `type: link`
Pure placeholder. The pipeline does not fetch anything; the reader page shows
a static "visit site" card. Use this for JS-rendered sites where neither RSS
nor `web` extraction works (e.g. Anthropic News, DeepSeek). A future RSSHub
instance is the planned replacement.

```yaml
- name: Anthropic News
  url: https://www.anthropic.com/news
  category: AI Research
  type: link
  language: en
  group: vendor
```

### `type: hotlist`
Reserved for hot-list sources. As of this writing the hot-list pipeline
(`fetch_hotlist.py`) does **not** read `sources.yaml` — its sources are still
hardcoded in a `SOURCES` list inside the script (see `docs/architecture.md`
TD-7). The `hotlist` value is accepted in `sources.yaml` as a forward-looking
type once the hot-list pipeline is migrated to config.

## The `group` field

`group` decides where a source appears on the reader page (`reader/index.html`):

- `blog` (default) — personal blog section. 30-day-stale blogs are folded
  behind a divider.
- `vendor` — vendor/lab section, rendered as a separate group above blogs.
  Stale folding still applies but the visual treatment differs.

Set `group: vendor` for official company/lab feeds (OpenAI Blog, DeepMind,
Anthropic, DeepSeek). Leave it off (or set `group: blog`) for individuals.

## Adding a new source

1. Open [`sources.yaml`](../sources.yaml).
2. Add a new entry under `sources:`. Required fields: `name`, `url`,
   `category`, `type`. Add `language` and `group` if applicable.
3. (Optional) Group it visually with related entries via a `# --- Section ---`
   comment.
4. Run locally to confirm it parses and fetches:
   ```bash
   python scripts/fetch_feeds.py --hours 72 \
     --web-cache data/web_seen.json \
     --reader-out _data/latest_entries.json
   ```
   Check that the source appears in `/tmp/feed_entries.json` `stats` with
   `status: "ok"`.
5. Commit `sources.yaml` and push. The next scheduled `daily.yml` run picks it
   up automatically.

## Removing or renaming a source

### Removing
1. Delete the entry from `sources.yaml`.
2. (Optional) Trim its key from `data/web_seen.json` if it was `type: web`.
   Leaving stale keys is harmless but accrues over time.
3. Historical data is **not** rewritten:
   - Past `_digests/YYYY-MM-DD.md` files keep the old source name in their
     content.
   - `_data/latest_entries.json` is fully rewritten on each fetch, so the
     removed source disappears from the reader page on the next run.
   - `data/source_stats.json` is append-only and retains historical entries.

### Renaming
A rename is treated as "remove old + add new" by the pipeline. Specifically:

- The web-seen cache (`data/web_seen.json`) keys on source name, so renamed
  `type: web` sources will re-report their existing articles as new on the
  first run after rename. Either accept the one-time noise, or hand-edit
  `data/web_seen.json` to rename the key before pushing.
- Source-stats history (`data/source_stats.json`) under the old name is not
  migrated; new stats accumulate under the new name.
- Past digests keep the old name in their text.

If continuity matters, prefer editing only the `name` field while keeping the
`url` (and the `web_seen.json` key) consistent with the old name, or
manually port the cache key.
