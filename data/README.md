# data/ 目录说明

本目录存放**可复现的原始数据与处理结果**，并明确标注来源与限制。

## 布局

```text
data/raw/<app_id>/
    app.json                     应用元数据（Lookup，带来源信封）
    reviews-mostRecent-p1.json   中国区 RSS 原始响应（间歇可用，采集器自动重试，每页约 35 条）
    reviews-amp-page-cn.json     App Store 产品页内嵌评论（中国区页面，8 条）
    reviews-itml-*.json          WebObjects userReviewsRow 响应（美国区批次，用于多源合并）
    collection_notes.json        每次采集的统计与注意事项
    imported-reviews.json        导入的外部数据集（source=import）
data/processed/<app_id>/
    reviews_clean.json           清洗去重后的结构化评论
    reviews_clean.csv            同上，CSV 版
    stats.json                   清洗统计（去重率、垃圾数、语言分布等）
```

## 标签约定

- `source=rss`：Apple iTunes Customer Reviews RSS（中国区 cn 可用，每页约 35 条；美国区已停用）。
- `source=amp-page`：App Store 产品页内嵌的用户评论（部分 storefront 如中国区页面返回 8 条）。
- `source=itml`：Apple iTunes WebObjects userReviewsRow 官方接口（美国区，默认停用，仅显式 us 链接使用）。
- `source=import`：外部导入的合规 JSON/CSV 数据集。
- `fetched_at`：抓取/导入时间。
- `url`：原始数据来源地址。

## 诚实声明

如果某次采集因网络/地区限制返回空数据，`collection_notes.json` 会如实记录空页与原因，
不会用编造数据填充。中国区采集为多源合并：cn RSS（自动重试）→ 产品页内嵌评论 → 美国区 itml，
去重后通常 35+ 条；批量数据请通过 GitHub Actions 定时采集或 JSON/CSV 导入。
