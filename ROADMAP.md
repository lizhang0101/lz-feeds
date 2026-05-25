# Roadmap

## 下一步

### 1. summarize.py — 摘要生成脚本

调用 LLM API，把 `fetch_feeds.py` 的 JSON 输出转换成摘要 Markdown。

- 输入：`/tmp/feed_entries.json`
- 输出：`digests/YYYY-MM-DD.md`
- 逻辑：和现有 feeds skill 的评分/摘要标准一致（中文摘要、1-5 分制、标签）
- 去重：对照上一份摘要中的 ⭐/📖 URL，避免重复推荐

### 2. GitHub Actions workflow

文件：`.github/workflows/daily.yml`

- 触发：cron，每天 UTC 01:00（北京时间 09:00）
- 步骤：
  1. checkout
  2. `pip install` 依赖
  3. 运行 `fetch_feeds.py --hours 24`
  4. 运行 `summarize.py`
  5. 更新 `data/source_stats.json`
  6. commit & push `digests/` 和 `data/`

Secrets 需要在仓库设置中添加：`LLM_API_KEY`

### 3. GitHub Pages

- 用 [MkDocs](https://www.mkdocs.org/) 或 [Jekyll](https://jekyllrb.com/) 渲染 `digests/` 目录
- 首页显示摘要列表（按日期倒序）
- 每篇摘要有独立 URL
- 推荐 MkDocs + Material 主题，配置简单，移动端友好

### 4. Todoist 集成（可选）

每次 workflow 运行后，自动创建一条 Todoist 任务：
- 标题：`📰 信息摘要 YYYY-MM-DD`
- 内容：当日 Pages 链接

### 5. 迁移收尾

- 更新 `claude-agent/skills/feeds/SKILL.md`，指向新仓库的工作流程
- Obsidian `feeds/` 目录可以归档或停止写入
