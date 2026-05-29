---
layout: default
title: 首页
---

个人信息摘要。{% if site.data.latest_entries %}最后更新：{{ site.data.latest_entries.fetched_at_beijing | default: site.data.latest_entries.fetched_at | slice: 0, 16 }} 北京时间{% endif %}

| 版块 | 说明 | 更新频率 |
|------|------|----------|
| [📡 RSS 阅读]({{ '/reader/' | relative_url }}) | 72小时内所有订阅源的新文章 | 每日 |
| [📰 每日摘要]({{ '/digests/' | relative_url }}) | AI 评分筛选的重点推荐 | 每日 |
| [🔥 热榜]({{ '/hotlist/' | relative_url }}) | 知乎热榜实时数据 | 每2小时 |
