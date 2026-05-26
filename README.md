# lz-feeds

个人信息阅读站，由 GitHub Actions 自动运行，Gemini API 生成中文摘要，GitHub Pages 展示。

**Pages：** https://lizhang0101.github.io/lz-feeds/

## 功能

- **RSS 阅读**：展示所有订阅源的近期文章（每源 5 条），按更新时间排序，分厂商 / 个人博客两组；30 天未更新的博客折叠到分隔线下方；Gemini 生成中文摘要，新文章（72h 内）加 NEW 标记
- **每日摘要**：每天 08:17（北京时间）自动抓取 72h 内新文章，Gemini 打分（1-5）并生成中文摘要，重点推荐 5 篇 + 扩展阅读 5 篇
- **知乎热榜**：每 2 小时自动抓取，实时更新

## 目录结构

```
lz-feeds/
├── sources.yaml              # RSS 订阅源配置
├── scripts/
│   ├── fetch_feeds.py        # RSS 抓取；--reader-out 输出按源分组的阅读器 JSON
│   ├── fetch_hotlist.py      # 热榜抓取
│   └── summarize.py          # Gemini 摘要；--enrich-reader 为阅读器条目生成 AI 摘要
├── _digests/                 # Jekyll collection：每日摘要
│   └── YYYY-MM-DD.md
├── _hotlist/                 # Jekyll collection：热榜快照
│   └── zhihu.md
├── _data/
│   └── latest_entries.json   # 阅读器数据（按源分组，含 AI 摘要）
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
    ├── daily.yml             # 每日摘要 + 阅读器更新（UTC 00:17）
    ├── hotlist.yml           # 热榜更新（每 2 小时）
    └── pages.yml             # GitHub Pages 部署
```

## 本地运行

```bash
pip install -r requirements.txt

# 抓取 RSS 并生成阅读器数据
python scripts/fetch_feeds.py --hours 72 --web-cache data/web_seen.json \
  --reader-out _data/latest_entries.json

# 为阅读器条目生成 AI 摘要（已有摘要的条目自动跳过）
GEMINI_API_KEY=your_key python scripts/summarize.py \
  --enrich-reader _data/latest_entries.json

# 生成每日摘要
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

编辑 `sources.yaml`，支持四种类型：

```yaml
- name: 示例博客
  url: https://example.com/feed.xml
  category: 分类名
  type: rss       # rss：RSS/Atom feed
                  # web：HTML 页面（解析文章链接）
                  # link：仅显示跳转链接，不抓取（适合 JS 渲染的站）
                  # hotlist：热榜源
  language: en    # en | zh
  group: blog     # blog（默认）| vendor（厂商，显示在独立分组）
```

## 添加热榜源

在 `scripts/fetch_hotlist.py` 的 `SOURCES` 列表中添加新平台，并实现对应的 `parse_<platform>()` 函数。

## Roadmap

### 已知问题
- **Anthropic / DeepSeek 无 RSS**：两个站点是 JS 渲染，目前以 `type: link` 占位。根本解法是自托管 RSSHub 实例
- **Node.js 20 deprecation warning**：`pages.yml` 中 Actions 版本触发 GitHub 警告，升级 action 版本可消除

### 待改进
- **更多热榜源**：微博、V2EX、Hacker News 等，在 `fetch_hotlist.py` 中添加对应解析函数
- **RSSHub 自托管**：为 Anthropic、DeepSeek 等 JS 渲染站点生成 RSS，替换当前 `type: link` 占位
- **阅读器增强**：关键词搜索 / 过滤、条目折叠展开、已读标记
- **摘要质量**：用户反馈机制，优化 prompt
