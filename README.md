# App Review Insights

把真实的 App Store 用户评论，自动变成**可追溯的产品需求（PRD）、版本规划和测试用例**。

> 目标与评估标准见 [PLAN.md](PLAN.md)，其源头是
> [retro-labs/app-review-insights](https://github.com/retro-labs/app-review-insights/blob/main/README.md)。

## 当前进度（M1-M3）

- [x] M0 项目骨架：git 仓库、目录结构、`.env.example`、CI 占位
- [x] M1 数据采集：Apple Lookup（元数据）+ Customer Reviews RSS（美国区评论），限速、缓存、断点续采
- [x] M1 数据导入：支持 JSON / CSV 评论数据集导入（README 硬性要求）
- [x] M1 清洗去重：字段规范化、去重、垃圾过滤、PII 脱敏、语言启发式识别
- [x] M2 分析层：动态主题发现（TF-IDF/模型嵌入 + 聚类 + LLM 命名）、
  证据化发现（引用白名单、置信度、冲突、provenance 区分统计与模型）
- [x] M3 规划层：需求生成（优先级/版本拆分）、Gherkin 测试用例、
  追溯校验（孤儿结论删除 / 无支持需求标 assumption / 校验报告）
- [x] M4 应用层：零依赖 Web UI（纯标准库服务器 + 原生 JS），
  支持进度流展示、交付物 Tab、JSON/CSV 导入；FastAPI/React 为可选升级
- [x] M5 部分：E2E 场景测试（混合语言/证据不足/模型失败/重复冲突）、
  [docs/EVALUATION.md](docs/EVALUATION.md) 评估自检、`scripts/self_check.py` 一键自检
- [x] M5 收尾：真实模型（DeepSeek）端到端验证、GitHub 推送与定时采集、Web UI 演示

## 快速开始

需要 Python 3.10+，M1 阶段**零第三方依赖**（纯标准库）。

```bash
# 1) 采集元数据 + 评论（US 区），结果缓存到 data/raw/<app_id>/
PYTHONPATH=src python scripts/fetch_reviews.py 839285684

# 2) 或者导入已有 JSON/CSV 数据集
PYTHONPATH=src python scripts/import_reviews.py path/to/reviews.csv --app-id 839285684

# 3) 清洗去重，输出 data/processed/<app_id>/
PYTHONPATH=src python scripts/clean_reviews.py 839285684

# 4) 运行测试（M1 用标准库 unittest，pytest 也能收集）
PYTHONPATH=src python -m unittest discover -s tests -v

# 5) 运行完整分析流水线（S0 范围 -> S8 汇总）
#    未配置 LLM 时自动降级为确定性模式；配置 .env 后自动启用模型驱动
PYTHONPATH=src python scripts/analyze.py 839285684 --goal "订阅转化与付费墙体验"
PYTHONPATH=src python scripts/analyze.py 839285684 --no-llm

# 6) 启动 Web UI（纯标准库，零第三方依赖）
python app/server.py --port 8765
# 打开 http://127.0.0.1:8765
```

示例应用（评估用主样例）：`Workout for Women: Home & Gym`
`https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684`

分析结果输出到 `data/processed/<app_id>/analysis/`，包含：范围、清洗统计、
动态主题、带证据的发现、需求（PRD）、测试用例、追溯校验报告、进度事件。

模型设计（提示词、防幻觉、失败处理、无硬编码承诺）见 [docs/AI.md](docs/AI.md)。

## Web UI（M4）

启动 `python app/server.py` 后打开 `http://127.0.0.1:8765`：

- 输入美国区 App Store 链接或应用 ID + 分析目标，点击「开始分析」；
- 页面实时展示 S0-S8 阶段进度（轮询 `/api/status/<run_id>`）；
- 完成后通过 Tab 查看：摘要 / 动态主题 / 带证据的发现 / 需求 PRD / 测试用例 /
  追溯校验报告 / 清洗后数据；
- 「统计 / 模型 / 假设 / 已移除」用不同徽章区分（README R6）；
- 支持直接上传 JSON/CSV 评论数据集再分析（README R10）；
- 未配置 LLM 时自动进入确定性模式，界面明确提示，不伪装成功。

服务器与前端均为纯标准库实现（`app/server.py` + `app/static/`），无需 npm/pip 安装。

## 数据来源与限制（重要）

### 数据来源

- **应用元数据**：Apple iTunes Search API（Lookup），`https://itunes.apple.com/lookup?id=<id>&country=us`
- **评论数据**：优先使用 Apple iTunes WebObjects 官方接口（`userReviewsRow`，美国区 storefront），
  `https://itunes.apple.com/WebObjects/MZStore.woa/wa/userReviewsRow?id=<id>&displayable-kind=11&sortId=4&pageNumber=0`
  - 该接口无需 token、不受地理重定向影响，2026 年实测可用，返回真实评论（正文/评分/日期/投票数）
  - 旧版 Customer Reviews RSS 与 AMP Reviews API 已被苹果停用（RSS 对任意应用返回空 feed），仅作兜底保留
  - 部分 storefront（如中国区产品页）会内嵌 8 条真实评论，采集器也会读取（`reviews-amp-page-cn.json`）

输入链接可以是美区或中国区页面（如 `https://apps.apple.com/cn/app/.../id839285684`），
链接只用于识别应用 ID；**评论数据始终从美国区商店（`country=us`）采集**，符合 README 要求。

### 已知限制（实测）

在部分网络环境（如中国大陆直连）下，旧版 RSS/AMP 接口不可用；采集器会自动回退到
WebObjects `userReviewsRow` 接口（本仓库 2026-08 实测可直接取数）。补充对策：

1. 使用仓库内 [.github/workflows/collect-reviews.yml](.github/workflows/collect-reviews.yml)
   的定时采集（`--method itml`），结果自动提交到 `data/raw/`；
2. 使用导入功能（JSON/CSV）喂入合规数据集；
3. 在可直连的网络环境本地直接运行 `fetch_reviews.py --method itml`。

缓存文件统一使用信封结构记录来源：

```json
{ "app_id": "...", "url": "https://...", "fetched_at": "...", "data": { ... } }
```

**缓存数据仅用于离线评审与复现，绝不冒充实时采集，也绝不编造评论。**

## 导入格式

JSON（数组，或带 `feed.entry` 的 RSS 结构，或 `{data: [...]}` 信封）与 CSV 均可。
字段名支持常见别名，最小要求有正文或标题：

```text
id / review_id / reviewId      评论 ID（用于去重，缺省时按 作者+日期+内容 哈希去重）
author / author_name / name    作者
rating / stars / im:rating     1-5 星
title / title.label            标题
content / body / text          正文
version / appVersion           版本
updated / date / created_at    时间
votes / helpful_votes          有用票数（可选）
country / storefront           地区（默认 us）
```

## 目录结构

```text
src/app_review_insights/   核心代码（collector / importer / cleaner / models / storage）
scripts/                   命令行入口（fetch / import / clean）
tests/                     单元测试
data/raw/<app_id>/         原始缓存（可复现数据）
data/processed/<app_id>/   清洗后结构化结果
docs/                      架构与决策文档（后续里程碑补充）
.github/workflows/         CI 与定时采集
```

## 密钥与配置

复制 `.env.example` 为 `.env` 并填写（M2 起需要 LLM 配置）。真实密钥绝不提交到仓库。

## Roadmap

详见 [PLAN.md](PLAN.md) 第 10 节：M0 基建 → M1 数据层 → M2 分析层 → M3 规划层 → M4 应用层 → M5 交付加固。
