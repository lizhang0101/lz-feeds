# lz-feeds

每日 RSS 摘要 + 实时热榜，由 GitHub Actions 自动运行，Gemini API 生成中文摘要，GitHub Pages 展示。

**Pages：** https://lizhang0101.github.io/lz-feeds/

## 功能

- **每日摘要**：每天 09:00（北京时间）自动抓取 RSS/Atom 订阅源，Gemini 打分（1-5）并生成中文摘要，重点推荐 5 篇 + 扩展阅读 5 篇
- **知乎热榜**：每 2 小时自动抓取，实时更新

## 目录结构

```
lz-feeds/
├── sources.yaml              # RSS 订阅源配置
├── scripts/
│   ├── fetch_feeds.py        # RSS 抓取脚本
│   ├── fetch_hotlist.py      # 热榜抓取脚本
│   ├── summarize.py          # Gemini 摘要生成
│   └── gen_index.py          # Pages 构建：生成 docs/
├── data/
│   ├── source_stats.json     # 历史统计
│   └── web_seen.json         # web 源去重缓存
├── digests/                  # 每日摘要
│   └── YYYY-MM-DD.md
├── hotlist/                  # 热榜快照
│   └── zhihu.md
├── mkdocs.yml                # MkDocs 配置
└── .github/workflows/
    ├── daily.yml             # 每日摘要（UTC 01:00）
    ├── hotlist.yml           # 热榜更新（每 2 小时）
    └── pages.yml             # GitHub Pages 部署
```

## 本地运行

```bash
pip install -r requirements.txt

# RSS 摘要
python scripts/fetch_feeds.py --hours 24
GEMINI_API_KEY=your_key python scripts/summarize.py

# 热榜
python scripts/fetch_hotlist.py
```

## 配置

在 GitHub 仓库 Settings → Secrets → Actions 中设置：

- `GEMINI_API_KEY` — Google Gemini API key（[免费额度](https://aistudio.google.com)即可）

## 添加订阅源

编辑 `sources.yaml`，支持三种类型：

```yaml
- name: 示例博客
  url: https://example.com/feed.xml
  category: 分类名
  type: rss       # rss | web | hotlist
  language: en    # en | zh
```

## 添加热榜源

在 `scripts/fetch_hotlist.py` 的 `SOURCES` 列表中添加新平台，并实现对应的 `parse_<platform>()` 函数。
