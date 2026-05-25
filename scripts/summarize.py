#!/usr/bin/env python3
"""Generate daily digest markdown from feed entries JSON using Gemini API.

Usage:
    python summarize.py [--input PATH] [--output PATH] [--model MODEL]
                        [--top N] [--extended N] [--digests-dir PATH]

Defaults:
    --input       /tmp/feed_entries.json
    --output      digests/YYYY-MM-DD.md  (repo root)
    --model       gemini-2.5-flash
    --top         5
    --extended    5

Environment:
    GEMINI_API_KEY — Google Gemini API key (required)
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from google import genai
from google.genai import types


SYSTEM_PROMPT = """\
You are a personal information curator. Score and summarize RSS feed entries for a technical reader interested in: AI/LLM research and safety, software engineering, distributed systems, programming languages, open source, tech culture.

Scoring:
  5 = Must-read: major insight, important development, or novel perspective
  4 = Valuable: worth reading soon
  3 = Mildly interesting: worth bookmarking
  2 = Routine: minor update, short link post, low substance
  1 = Irrelevant: navigation/team/index pages, off-topic content

Return a JSON array. One object per entry, same order as input.
Every object must have: "link" (copy from input), "score" (integer 1–5).
Objects with score >= 4 must also include:
  "summary": 1–2 sentence Chinese summary, ≤120 chars, factual and specific
  "tags": array of 3–5 English hashtags, lowercase-hyphenated, no # prefix\
"""


def get_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("Error: set GEMINI_API_KEY")
    return key


def get_prev_featured(digests_dir: Path, today: str) -> set[str]:
    """URLs featured as ⭐ or 📖 in the most recent previous digest."""
    try:
        files = sorted(digests_dir.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].md"))
        prev_files = [f for f in files if f.stem < today]
        if not prev_files:
            return set()
        content = prev_files[-1].read_text(encoding="utf-8")
        # Only the featured sections, not the full table
        cut = content.find("## 📰 全部条目")
        if cut != -1:
            content = content[:cut]
        return set(re.findall(r'\]\((https?://[^)]+)\)', content))
    except Exception:
        return set()


def call_llm(client: genai.Client, entries: list[dict], model: str) -> dict[str, dict]:
    """Score and summarize entries. Returns dict keyed by link."""
    payload = [
        {
            "link": e["link"],
            "source": e["source"],
            "title": e["title"],
            "snippet": (e.get("content") or "")[:400],
        }
        for e in entries
        if e.get("link")
    ]

    response = client.models.generate_content(
        model=model,
        contents=f"Score these {len(payload)} entries:\n\n{json.dumps(payload, ensure_ascii=False)}",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=8192,
        ),
    )

    text = response.text
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        print("Warning: LLM response didn't contain a JSON array", file=sys.stderr)
        return {}
    try:
        result = json.loads(match.group())
        return {item["link"]: item for item in result if "link" in item}
    except json.JSONDecodeError as exc:
        print(f"Warning: JSON parse error: {exc}", file=sys.stderr)
        return {}


def fmt_long(date_str: str | None) -> str:
    """YYYY-MM-DD or —"""
    return date_str[:10] if date_str else "—"


def fmt_short(date_str: str | None) -> str:
    """MM-DD or —"""
    return date_str[5:10] if date_str else "—"


def group_by_source(entries: list[dict]) -> list[tuple[str, list[dict]]]:
    """Group preserving first-appearance order."""
    buckets: dict[str, list[dict]] = {}
    order: list[str] = []
    for e in entries:
        src = e["source"]
        if src not in buckets:
            buckets[src] = []
            order.append(src)
        buckets[src].append(e)
    return [(src, buckets[src]) for src in order]


def render(
    entries: list[dict],
    scores: dict[str, dict],
    meta: dict,
    today: str,
    top_n: int,
    extended_n: int,
    prev_featured: set[str],
) -> str:
    for e in entries:
        info = scores.get(e["link"], {})
        e["_score"] = info.get("score", 2)
        e["_summary"] = info.get("summary", "")
        e["_tags"] = info.get("tags", [])
        e["_flag"] = "—"

    eligible = [e for e in entries if e["link"] not in prev_featured]
    by_score = sorted(eligible, key=lambda x: x["_score"], reverse=True)

    top_picks = [e for e in by_score if e["_score"] >= 4][:top_n]
    top_links = {e["link"] for e in top_picks}

    extended = [
        e for e in by_score
        if e["link"] not in top_links and e["_score"] >= 3
    ][:extended_n]
    ext_links = {e["link"] for e in extended}

    for e in entries:
        if e["link"] in top_links:
            e["_flag"] = "⭐"
        elif e["link"] in ext_links:
            e["_flag"] = "📖"

    L: list[str] = []

    # Frontmatter
    L += [
        "---",
        f"date: {today}",
        f"sources_checked: {meta.get('sources_checked', 0)}",
        f"entries_found: {meta.get('entries_found', 0)}",
        f"top_picks: {len(top_picks)}",
        f"extended: {len(extended)}",
        "---",
        "",
        f"# 信息摘要 {today}",
        "",
    ]

    # ⭐ Top picks
    L.append(f"## ⭐ 重点推荐 (top {len(top_picks)})")
    L.append("")
    for src, group in group_by_source(top_picks):
        L.append(f"### {src}")
        L.append("")
        for e in group:
            tags = " ".join(f"#{t.lstrip('#')}" for t in e["_tags"]) if e["_tags"] else ""
            L.append(f"**[{e['title']}]({e['link']})** | {fmt_long(e.get('parsed_date'))} | {e['_score']}/5")
            if e["_summary"]:
                L.append(e["_summary"])
            if tags:
                L.append(f"**标签:** {tags}")
            L.append("")

    L += ["---", ""]

    # 📖 Extended
    L.append("## 📖 扩展阅读")
    L.append("")
    for src, group in group_by_source(extended):
        L.append(f"### {src}")
        L.append("")
        for e in group:
            L.append(f"**[{e['title']}]({e['link']})** | {fmt_long(e.get('parsed_date'))} | {e['_score']}/5")
            if e["_summary"]:
                L.append(e["_summary"])
            L.append("")

    L += ["---", ""]

    # 📰 Full table
    L.append("## 📰 全部条目 (按来源分组)")
    L.append("")
    for src, group in group_by_source(entries):
        L.append(f"### {src}")
        L.append("")
        L.append("| 日期 | 标题 | 评分 | 备注 |")
        L.append("|------|------|------|------|")
        for e in group:
            title = e["title"][:60].replace("|", "&#124;")
            L.append(
                f"| {fmt_short(e.get('parsed_date'))} "
                f"| [{title}]({e['link']}) "
                f"| {e['_score']}/5 "
                f"| {e['_flag']} |"
            )
        L.append("")

    return "\n".join(L)


def main():
    parser = argparse.ArgumentParser(description="Summarize feed entries into daily digest")
    parser.add_argument("--input", type=Path, default=Path("/tmp/feed_entries.json"))
    parser.add_argument("--output", type=Path, default=None,
                        help="Output path (default: digests/YYYY-MM-DD.md in repo root)")
    parser.add_argument("--model", default="gemini-2.5-flash",
                        help="Gemini model ID")
    parser.add_argument("--top", type=int, default=5, help="Number of top picks")
    parser.add_argument("--extended", type=int, default=5, help="Number of extended reads")
    parser.add_argument("--digests-dir", type=Path, default=None,
                        help="Directory with past digests for dedup (default: beside output)")
    args = parser.parse_args()

    if not args.input.exists():
        sys.exit(f"Error: {args.input} not found")

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("entries", [])
    if not entries:
        print("No entries to process")
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    repo_root = Path(__file__).parent.parent
    output = args.output or (repo_root / "digests" / f"{today}.md")
    digests_dir = args.digests_dir or output.parent

    prev_featured = get_prev_featured(digests_dir, today)
    if prev_featured:
        print(f"Previously featured: {len(prev_featured)} URLs (excluded from top/extended)")

    client = genai.Client(api_key=get_api_key())
    print(f"Scoring {len(entries)} entries with {args.model}...")
    scores = call_llm(client, entries, args.model)
    print(f"  Received scores for {len(scores)} entries")

    md = render(entries, scores, data, today, args.top, args.extended, prev_featured)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(md, encoding="utf-8")
    print(f"Written: {output}")


if __name__ == "__main__":
    main()
