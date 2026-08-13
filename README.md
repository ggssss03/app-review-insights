# App Review Insights

把真实的 App Store 用户评论，自动转化为**可追溯的产品需求（PRD）、版本规划和测试用例**，
并通过一个**零第三方依赖、本地一键运行的 Web UI** 展示完整分析流程。

评估用主样例：

```text
https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684
```

> 本项目的目标与验收标准来自 LaienTech 评估书。每一项要求如何满足，见
> [docs/EVALUATION.md](docs/EVALUATION.md)；实施与架构设计见 [PLAN.md](PLAN.md)；
> 模型与防幻觉设计见 [docs/AI.md](docs/AI.md)。

## 能做什么

1. 在 UI 中输入一个**有效的美国区 App Store 链接**，可选填分析目标/约束
   （如「订阅转化与付费墙体验」「低分评论」「指定版本」），点击「开始分析」。
2. 系统自动完成 10 步工作流：
   **范围解析 → 采集/导入 → 清洗去重 → 动态分类 → 证据评估 → 版本规划/PRD →
   测试用例 → 追溯校验 → 进度展示 → 交付物展示**。
3. 所有分类、发现、需求、用例都由当前数据动态生成，**没有任何 app 专属硬编码**。
4. 每个发现都带证据评论 ID、样本数、置信度、不确定性、冲突，并区分
   「确定性统计 / 模型生成 / 假设 / 已移除」。
5. 支持导入合规的 JSON/CSV 评论数据集，换链接、换数据集、换目标都能运行。
6. 未配置 LLM 时自动降级为确定性模式并明确标注，绝不伪装成功。

## 快速开始

需要 Python 3.10+，运行阶段**零第三方依赖**（纯标准库 + 原生 HTML/CSS/JS）。

```bash
# 1) 采集元数据与评论（美国区官方接口，示例 app）
PYTHONPATH=src python scripts/fetch_reviews.py 839285684 --country us --method itml

# 2) 或导入已有 JSON/CSV 评论数据集
PYTHONPATH=src python scripts/import_reviews.py path/to/reviews.csv --app-id 839285684

# 3) 清洗去重，输出 data/processed/<app_id>/
PYTHONPATH=src python scripts/clean_reviews.py 839285684

# 4) 运行完整分析流水线（S0 → S8）
PYTHONPATH=src python scripts/analyze.py 839285684 --goal "订阅转化与付费墙体验"

# 5) 运行测试与一键自检
PYTHONPATH=src python -m unittest discover -s tests -v   # 75 个用例
python scripts/self_check.py

# 6) 启动 Web UI
python app/server.py --port 8765
# 打开 http://127.0.0.1:8765
```

离线评审时无需网络：仓库已包含示例 app 的元数据、原始评论缓存与完整分析产物。

## 数据来源与限制（如实声明）

- **元数据**：Apple iTunes Lookup API（美国区）。
- **评论**：Apple iTunes WebObjects `userReviewsRow` 官方接口（美国区 storefront）。
- **当前限制**：该接口固定只返回 10 条热门评论，且不返回每条评论的版本号；
  旧版美区 RSS 已停用，AMP 评论 token 当前不可获取。以上限制已写入
  `data/raw/<app_id>/collection_notes.json`，报告与 UI 也会如实展示，**绝不编造评论**。
- **导入兜底**：支持 JSON/CSV 评论数据集导入；更丰富的美区样本可由此补充。
- **数量上限**：评论不足 200 条全量使用；超过 200 条只取前 200 条。
- **礼貌限速**：请求间隔 ≥ 1 秒，原始响应按页缓存，支持断点续采。

缓存数据结构统一为信封格式（`url` / `fetched_at` / `data`），保证来源可溯源。

## 导入格式

JSON（评论数组、RSS `feed.entry` 结构或 `{data:[...]}` 信封）与 CSV 均可，
最小要求有正文或标题。字段别名见下表：

| 含义 | 可用字段名 |
| --- | --- |
| 评论 ID | `id` / `review_id` / `reviewId` |
| 作者 | `author` / `author_name` / `name` |
| 评分 | `rating` / `stars` / `im:rating`（1–5） |
| 标题 | `title` / `title.label` |
| 正文 | `content` / `body` / `text` |
| 版本 | `version` / `appVersion` |
| 时间 | `updated` / `date` / `created_at` |
| 有用票 | `votes` / `helpful_votes`（可选） |
| 地区 | `country` / `storefront`（默认 us） |

## Web UI

`python app/server.py` 后打开 `http://127.0.0.1:8765`：

- 首页：美区链接/应用 ID + 分析目标 + JSON/CSV 导入 + Start；
- 进度页：S0–S8 阶段状态、耗时、错误与重试；
- 结果页 Tab：摘要 / 原始评论 / 主题聚类 / 关键发现 / 需求 PRD / 验收用例 / 溯源校验 / 数据清洗；
- 摘要含 KPI、评分环形图、语言分布、分析范围、运行模式与溯源通过率；
- 发现页支持证据点击查看原文、低置信折叠、追问与反例挑战；
- 需求页含版本甘特与 PRD 评审（接受 / 标记假设 / 删除 + 批注）；
- 溯源页含全链路 SVG 图、逐项检查与引用白名单拦截记录；
- 支持全局筛选（星级 / 语言 / 版本）、S0–S8 侧栏导航、演示模式、Markdown/JSON 一键导出。

## 目录结构

```text
app/server.py                零依赖 Web 服务器（REST + 后台流水线）
app/static/                  原生 HTML/CSS/JS 前端
src/app_review_insights/     核心代码（采集/导入/清洗/分析/规划/校验/LLM）
scripts/                     命令行入口（fetch / import / clean / analyze / self_check）
tests/                       75 个单元/集成测试
data/raw/<app_id>/           原始缓存与采集说明
data/processed/<app_id>/     清洗结果与分析产物
docs/AI.md                   模型、提示词、配置与防幻觉设计
docs/EVALUATION.md           评估书要求逐项对照
PLAN.md                      实施计划与架构
design-system/               亮色全息设计系统（MASTER.md）
.github/workflows/           CI 测试与定时采集
```

## 密钥与配置

复制 `.env.example` 为 `.env` 并填写：

```text
LLM_PROVIDER=deepseek
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=
LLM_MODEL=deepseek-chat
```

密钥只走环境变量，真实 key 绝不提交仓库。未配置时系统进入确定性模式。

## 评估要求对照

评估书的 Background / Objective / AI Requirements / Deliverables / Technical
Requirements / Evaluation Criteria / Important Notes 每条要求与项目实现位置的
完整对照，见 [docs/EVALUATION.md](docs/EVALUATION.md)。
