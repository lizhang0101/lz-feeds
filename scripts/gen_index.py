#!/usr/bin/env python3
"""Build docs/ for MkDocs: copy digests + hotlist, generate index + RSS reader, write mkdocs.yml."""

import json
import shutil
import yaml
from pathlib import Path

root = Path(__file__).parent.parent
docs = root / "docs"

REPO = "lizhang0101/lz-feeds"
HOTLIST_REFRESH_URL = f"https://github.com/{REPO}/actions/workflows/hotlist.yml"
DAILY_REFRESH_URL = f"https://github.com/{REPO}/actions/workflows/daily.yml"

# ── Clean & scaffold ──────────────────────────────────────────────
if docs.exists():
    shutil.rmtree(docs)
for subdir in ("reader", "digests", "hotlist"):
    (docs / subdir).mkdir(parents=True)

# ── Collect source files ──────────────────────────────────────────
digest_files = sorted(
    (root / "digests").glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].md"),
    reverse=True,
)
for f in digest_files:
    shutil.copy(f, docs / "digests" / f.name)

hotlist_src = root / "hotlist"
hotlist_files = sorted(hotlist_src.glob("*.md")) if hotlist_src.exists() else []
for f in hotlist_files:
    shutil.copy(f, docs / "hotlist" / f.name)

# ── RSS Reader page ───────────────────────────────────────────────
latest_entries_path = root / "data" / "latest_entries.json"
reader_lines = ["# 📡 RSS 阅读", ""]

if latest_entries_path.exists():
    with open(latest_entries_path, encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("entries", [])
    fetched_at = data.get("fetched_at", "")[:16]
    cutoff_hours = data.get("cutoff_hours", 24)
    sources_checked = data.get("sources_checked", 0)

    reader_lines.append(
        f"_最后更新: {fetched_at} UTC &nbsp;·&nbsp; "
        f"{cutoff_hours}h 窗口 &nbsp;·&nbsp; "
        f"{len(entries)} 条 / {sources_checked} 个来源_"
    )
    reader_lines.append("")

    if entries:
        reader_lines += [
            "| 时间 | 来源 | 标题 | 分类 |",
            "|------|------|------|------|",
        ]
        for e in entries:
            raw_date = (e.get("parsed_date") or "")[:10]
            date_cell = raw_date[5:] if raw_date else "—"
            source = (e.get("source") or "").replace("|", "&#124;")
            title = (e.get("title") or "Untitled").replace("|", "&#124;")[:80]
            link = e.get("link", "")
            category = (e.get("category") or "").replace("|", "&#124;")
            title_cell = f"[{title}]({link})" if link else title
            reader_lines.append(f"| {date_cell} | {source} | {title_cell} | {category} |")
    else:
        reader_lines.append("_72小时内暂无新文章_")
else:
    reader_lines += [
        "_暂无数据，待每日摘要任务运行后自动更新_",
        "",
        f"[手动触发]({DAILY_REFRESH_URL})",
    ]

(docs / "reader" / "index.md").write_text("\n".join(reader_lines) + "\n", encoding="utf-8")

# ── Home page ────────────────────────────────────────────────────
index_lines = [
    "# lz-feeds",
    "",
    "个人信息摘要 · RSS 阅读 · 热榜",
    "",
    "---",
    "",
    f"## 📡 RSS 阅读 &nbsp; [🔄]({DAILY_REFRESH_URL} \"手动触发\")",
    "",
    "→ [查看最近文章](reader/index.md)",
    "",
    "---",
    "",
    "## 📰 每日摘要",
    "",
]
for f in digest_files[:10]:
    index_lines.append(f"- [{f.stem}](digests/{f.name})")
if len(digest_files) > 10:
    index_lines.append(f"- _（共 {len(digest_files)} 期，左侧导航查看更多）_")
index_lines += [
    "",
    "---",
    "",
    f"## 🔥 热榜 &nbsp; [🔄]({HOTLIST_REFRESH_URL} \"手动触发\")",
    "",
]
if hotlist_files:
    for f in hotlist_files:
        index_lines.append(f"- [{f.stem}](hotlist/{f.name})")
else:
    index_lines.append("_暂无热榜数据_")
index_lines.append("")

(docs / "index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

# ── mkdocs.yml (dynamic nav) ──────────────────────────────────────
digest_nav = [{f.stem: f"digests/{f.name}"} for f in digest_files]
hotlist_nav = [{f.stem: f"hotlist/{f.name}"} for f in hotlist_files]

nav = [
    {"首页": "index.md"},
    {"📡 RSS 阅读": "reader/index.md"},
    {"📰 每日摘要": digest_nav or [{"暂无数据": "index.md"}]},
    {"🔥 热榜": hotlist_nav or [{"暂无数据": "index.md"}]},
]

mkdocs_config = {
    "site_name": "lz-feeds",
    "site_description": "个人信息摘要",
    "docs_dir": "docs",
    "nav": nav,
    "theme": {
        "name": "material",
        "language": "zh",
        "features": [
            "navigation.instant",
            "navigation.top",
            "navigation.tabs",
            "navigation.indexes",
        ],
        "palette": {
            "scheme": "default",
            "primary": "indigo",
        },
    },
    "plugins": ["search"],
    "markdown_extensions": ["tables", "meta"],
}

(root / "mkdocs.yml").write_text(
    yaml.dump(mkdocs_config, allow_unicode=True, default_flow_style=False, sort_keys=False),
    encoding="utf-8",
)

print(
    f"Built docs/: {len(digest_files)} digests, {len(hotlist_files)} hotlists, "
    f"{len(entries) if latest_entries_path.exists() else 0} reader entries"
)
