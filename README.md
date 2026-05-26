# lz-feeds

每日 RSS 摘要 + 实时热榜，由 GitHub Actions 自动运行，Gemini API 生成中文摘要，GitHub Pages 展示。

**Pages：** https://lizhang0101.github.io/lz-feeds/

## 功能

- **每日摘要**：每天 08:17（北京时间）自动抓取 RSS/Atom 订阅源，Gemini 打分（1-5）并生成中文摘要，重点推荐 5 篇 + 扩展阅读 5 篇
- **知乎热榜**：每 2 小时自动抓取，实时更新

## 目录结构

```
lz-feeds/
├── sources.yaml              # RSS 订阅源配置
├── scripts/
│   ├── fetch_feeds.py        # RSS 抓取脚本
│   ├── fetch_hotlist.py      # 热榜抓取脚本
│   └── summarize.py          # Gemini 摘要生成
├── _digests/                 # Jekyll collection：每日摘要
│   └── YYYY-MM-DD.md
├── _hotlist/                 # Jekyll collection：热榜快照
│   └── zhihu.md
├── _data/
│   └── latest_entries.json   # RSS 阅读页数据（fetch_feeds.py 生成）
├── _layouts/                 # Jekyll 布局模板
├── assets/css/style.css      # 样式
├── data/
│   ├── source_stats.json     # 历史统计
│   └── web_seen.json         # web 源去重缓存
├── digests/index.html        # 摘要列表页
├── hotlist/index.html        # 热榜列表页
├── reader/index.html         # RSS 阅读页
├── index.md                  # 首页
├── _config.yml               # Jekyll 配置
├── Gemfile                   # Ruby 依赖
├── requirements.txt          # Python 依赖
└── .github/workflows/
    ├── daily.yml             # 每日摘要（UTC 00:17）
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

## 本地预览 Pages

```bash
bundle install
bundle exec jekyll serve
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
