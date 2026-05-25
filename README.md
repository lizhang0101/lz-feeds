# lz-feeds

每日 RSS 摘要，由 GitHub Actions 自动抓取，Anthropic API 生成中文摘要，GitHub Pages 展示。

## 目录结构

```
lz-feeds/
├── sources.yaml          # 订阅源配置
├── scripts/
│   ├── fetch_feeds.py    # RSS 抓取脚本
│   └── summarize.py      # 摘要生成脚本（调用 Anthropic API）
├── data/
│   ├── source_stats.json # 历史统计
│   └── web_seen.json     # web 源去重缓存
├── digests/              # 每日摘要 Markdown
│   └── YYYY-MM-DD.md
└── .github/
    └── workflows/
        └── daily.yml     # 自动化 workflow
```

## 使用方法

### 本地运行

```bash
pip install pyyaml anthropic
python scripts/fetch_feeds.py --hours 72 --output /tmp/feed_entries.json
python scripts/summarize.py --input /tmp/feed_entries.json --output digests/$(date +%F).md
```

### 自动化

GitHub Actions 每天 UTC 01:00（北京时间 09:00）自动运行，结果 commit 到 `digests/` 目录并发布到 GitHub Pages。

## 配置

在 GitHub 仓库 Settings → Secrets 中设置：

- `ANTHROPIC_API_KEY` — Anthropic API key
