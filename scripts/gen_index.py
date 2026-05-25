#!/usr/bin/env python3
"""Generate digests/index.md listing all digest files newest-first."""

from pathlib import Path

digests_dir = Path(__file__).parent.parent / "digests"
files = sorted(
    digests_dir.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].md"),
    reverse=True,
)

lines = ["# 信息摘要", ""]
for f in files:
    lines.append(f"- [{f.stem}]({f.name})")

(digests_dir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Generated index.md with {len(files)} entries")
