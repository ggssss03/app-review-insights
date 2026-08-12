# data/ 目录说明

本目录存放**可复现的原始数据与处理结果**，并明确标注来源与限制。

## 布局

```text
data/raw/<app_id>/
    app.json                     应用元数据（Lookup，带来源信封）
    reviews-itml-mostRecent-p0.json  WebObjects userReviewsRow 原始响应（美国区，当前可用）
    reviews-amp-page-cn.json     App Store 产品页内嵌评论（中国区页面，8 条）
    reviews-mostRecent-p1.json   旧版 RSS 原始响应（苹果已停用，通常为空）
    reviews-mostHelpful-p1.json
    collection_notes.json        每次采集的统计与注意事项
    imported-reviews.json        导入的外部数据集（source=import）
data/processed/<app_id>/
    reviews_clean.json           清洗去重后的结构化评论
    reviews_clean.csv            同上，CSV 版
    stats.json                   清洗统计（去重率、垃圾数、语言分布等）
```

## 标签约定

- `source=itml`：Apple iTunes WebObjects userReviewsRow 官方接口（美国区，当前可用，无需 token）。
- `source=amp-page`：App Store 产品页内嵌的用户评论（部分 storefront 如中国区页面返回 8 条）。
- `source=import`：外部导入的合规 JSON/CSV 数据集。
- `source=rss`：Apple 官方 Customer Reviews RSS（苹果已停用，保留仅为兼容）。
- `fetched_at`：抓取/导入时间。
- `url`：原始数据来源地址。

## 诚实声明

如果某次采集因网络/地区限制返回空数据，`collection_notes.json` 会如实记录空页与原因，
不会用编造数据填充。旧版 RSS 与 AMP 接口已失效时，工具会自动回退到 itml 接口；
批量数据请通过 GitHub Actions 定时采集或 JSON/CSV 导入。
