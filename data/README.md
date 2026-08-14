# data/ 目录说明

本目录存放**可复现的原始数据与处理结果**，并明确标注来源与限制。
仓库只缓存美国区主评估样例；中国区（cn）缓存已全部移除（本地与 GitHub 均不保留）。

## 布局

```text
data/raw/839285684/
    app.json                     应用元数据（Lookup，美区，带来源信封）
    reviews-itml-mostRecent-p0.json  WebObjects userReviewsRow 响应（美国区）
    collection_notes.json        每次采集的统计与注意事项
    imported-reviews.json        导入的外部数据集（source=import，如存在）
data/processed/839285684/
    reviews_clean.json           清洗去重后的结构化评论
    reviews_clean.csv            同上，CSV 版
    stats.json                   清洗统计（去重率、垃圾数、语言分布等）
    analysis/                    分析流水线各阶段产物（scope/topics/findings/requirements/testcases/traceability/summary/progress）
```

> 主评估样例 `839285684`（Workout for Women: Home & Gym）只使用美国区 `itml` 评论
> （Apple WebObjects userReviewsRow 官方接口，当前仅返回 10 条热门评论）；
> 该接口的分页参数已被苹果忽略，更多美区评论请通过 GitHub Actions 采集或导入合规数据集。
> 评估书要求评论数据必须来自美国区 storefront，因此仓库不缓存任何中区评论。

## 标签约定

- `source=itml`：Apple iTunes WebObjects userReviewsRow 官方接口（美国区）。
- `source=import`：外部导入的合规 JSON/CSV 数据集。
- `fetched_at`：抓取/导入时间。
- `url`：原始数据来源地址。
- 采集器代码仍支持 `rss` / `amp` 方式（主要适用于显式 `--country cn` 场景），但仓库不再缓存 cn 数据。

## 诚实声明

如果某次采集因网络/地区限制返回空数据，`collection_notes.json` 会如实记录空页与原因，
不会用编造数据填充。批量美区数据请通过 GitHub Actions 定时采集或 JSON/CSV 导入。
