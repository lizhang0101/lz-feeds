#!/usr/bin/env python3
"""Fetch hot lists and write to hotlist/<platform>.md."""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Make ``lib`` importable when run as ``python scripts/fetch_hotlist.py``.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.http import fetch_url  # noqa: E402


BEIJING_TZ = timezone(timedelta(hours=8))

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.zhihu.com/",
}

SOURCES = [
    {
        "platform": "zhihu",
        "name": "知乎热榜",
        "url": "https://www.zhihu.com/api/v3/feed/topstory/hot-list-web?limit=20&desktop=true",
        "headers": BROWSER_HEADERS,
    },
]


def parse_zhihu(raw: str) -> list[dict]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    items = []
    for i, item in enumerate(data.get("data", []), 1):
        target = item.get("target", {})
        title = (target.get("title_area", {}).get("text") or "").strip()
        url = target.get("link", {}).get("url", "")
        heat = target.get("metrics_area", {}).get("text", "")
        excerpt = ""
        if not title or not url:
            continue
        items.append({
            "rank": i,
            "title": title,
            "url": url,
            "heat": heat,
            "excerpt": excerpt,
        })
    return items


PARSERS = {
    "zhihu": parse_zhihu,
}


def render(name: str, items: list[dict], updated_at: str) -> str:
    lines = [
        "---",
        f"updated: {updated_at}",
        f"count: {len(items)}",
        "---",
        "",
        f"# {name}",
        "",
        f"> 更新时间：{updated_at}",
        "",
    ]
    for item in items:
        heat = f" — {item['heat']}" if item.get("heat") else ""
        lines.append(f"{item['rank']}. **[{item['title']}]({item['url']})**{heat}")
        if item.get("excerpt"):
            lines.append(f"   {item['excerpt']}")
        lines.append("")
    return "\n".join(lines)


def main():
    now = datetime.now(BEIJING_TZ)
    updated_at = now.strftime("%Y-%m-%d %H:%M 北京时间")
    output_dir = Path(__file__).parent.parent / "_hotlist"
    output_dir.mkdir(exist_ok=True)

    ok, failed = 0, 0
    for src in SOURCES:
        platform = src["platform"]
        print(f"Fetching {src['name']}...")
        raw = fetch_url(src["url"], headers=src.get("headers"))
        if not raw:
            print(f"  FAILED to fetch", file=sys.stderr)
            failed += 1
            continue
        items = PARSERS[platform](raw)
        if not items:
            print(f"  No items parsed", file=sys.stderr)
            failed += 1
            continue
        print(f"  Got {len(items)} items")
        md = render(src["name"], items, updated_at)
        (output_dir / f"{platform}.md").write_text(md, encoding="utf-8")
        ok += 1

    if failed and not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
