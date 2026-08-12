# data/ 目录说明

本目录存放**可复现的原始数据与处理结果**，并明确标注来源与限制。

## 布局

```text
data/raw/<app_id>/
    app.json                    应用元数据（Lookup，带来源信封）
    reviews-mostRecent-p1.json  评论 RSS 原始响应（带来源信封）
    reviews-mostHelpful-p1.json
    collection_notes.json       每次采集的统计与注意事项
    imported-reviews.json       导入的外部数据集（source=import）
data/processed/<app_id>/
    reviews_clean.json          清洗去重后的结构化评论
    reviews_clean.csv           同上，CSV 版
    stats.json                  清洗统计（去重率、垃圾数、语言分布等）
```

## 标签约定

- `source=rss`：Apple 官方 Customer Reviews RSS（美国区）。
- `source=import`：外部导入的合规 JSON/CSV 数据集。
- `fetched_at`：抓取/导入时间。
- `url`：原始数据来源地址。

## 诚实声明

如果某次采集因网络/地区限制返回空数据，`collection_notes.json` 会如实记录空页与原因，
不会用编造数据填充。离线评审时请优先参考通过 GitHub Actions 采集或导入的标注数据。
