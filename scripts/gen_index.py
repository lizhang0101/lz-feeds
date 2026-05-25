#!/usr/bin/env python3
"""Build docs/ for MkDocs: copy digests + hotlist, generate index."""

import shutil
from pathlib import Path

root = Path(__file__).parent.parent
docs = root / "docs"

if docs.exists():
    shutil.rmtree(docs)
docs.mkdir()

# Copy digests
digests_dst = docs / "digests"
digests_dst.mkdir()
digest_files = sorted(
    (root / "digests").glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].md"),
    reverse=True,
)
for f in digest_files:
    shutil.copy(f, digests_dst / f.name)

# Copy hotlist
hotlist_src = root / "hotlist"
hotlist_dst = docs / "hotlist"
hotlist_dst.mkdir()
hotlist_files = sorted(hotlist_src.glob("*.md")) if hotlist_src.exists() else []
for f in hotlist_files:
    shutil.copy(f, hotlist_dst / f.name)

# Generate index
lines = ["# lz-feeds", ""]

HOTLIST_REFRESH_URL = "https://github.com/lizhang0101/lz-feeds/actions/workflows/hotlist.yml"

lines += [f"## 🔥 热榜 · [🔄 手动刷新]({HOTLIST_REFRESH_URL})", ""]
if hotlist_files:
    for f in hotlist_files:
        lines.append(f"- [{f.stem}](hotlist/{f.name})")
else:
    lines.append("_暂无热榜数据_")
lines.append("")

lines += ["## 📰 信息摘要", ""]
for f in digest_files:
    lines.append(f"- [{f.stem}](digests/{f.name})")
lines.append("")

(docs / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Built docs/: {len(digest_files)} digests, {len(hotlist_files)} hotlists")
