# 评估书要求逐项对照

本文档把 LaienTech 评估书（`D:\README.md`）的每一项要求，对照到本项目的实现位置与验证方式。

## 1. Background（背景要求）

| 评估书要求 | 项目实现 | 验证 |
| --- | --- | --- |
| 使用真实 iOS 应用 workout-for-women-home-gym 作主样例 | UI 默认链接即为该应用，缓存数据见 `data/raw/839285684/` | 打开 UI 或查看 `data/raw/839285684/app.json` |
| 打开页面可用美区或中区链接 | UI 支持解析链接中的 app id 与 storefront | `extract_app_id` / `extract_country`（`collector.py`） |
| **评论数据必须来自美国区商店** | 主样例只保留美国区 `itml` 评论；中国区评论缓存已移除；CI 采集主样例用 `--country us` | `data/raw/839285684/collection_notes.json` 中 `country=us`；清洗结果全部 `country=us` |
| 完成「采集→清洗→分类→问题分析→版本规划→PRD→测试用例」并呈现在可运行 UI | S0–S8 流水线 + `app/server.py` Web UI | `python app/server.py` 端到端演示 |

## 2. Objective（目标与 10 步工作流）

| # | 评估书要求 | 实现位置 | 验证 |
| --- | --- | --- | --- |
| 1 | 根据目标与数据确定分析范围 | `analysis/scope.py`（规则种子 + LLM 抽取，失败回退全量） | `tests/test_scope.py` |
| 2 | 采集评论数据 | `collector.py`：Lookup + 美区 itml，限速/缓存/断点续采 | `tests/test_collector.py` |
| 3 | 清洗、去重、结构化 | `cleaner.py`：字段规范化、去重、垃圾过滤、PII 脱敏、语言识别 | `tests/test_cleaner.py` |
| 4 | 动态分类，不依赖固定关键词/预定义分类表 | `analysis/topics.py`：TF-IDF/KMeans 聚类（轮廓系数选 k）+ LLM 命名 | `tests/test_topics.py`；换数据集仍产出 |
| 5 | 评估证据充分性、冲突、不确定性、数据限制 | `analysis/findings.py`：样本数、冲突检测、置信度、uncertainty | `findings.json` 字段齐全 |
| 6 | 生成更新计划、PRD、必要时拆分版本 | `analysis/planning.py`：优先级 P0–P2、版本 V1/V2、验收标准 | `requirements.json` |
| 7 | 基于 PRD 生成测试用例，链接需求与来源评论 | `analysis/planning.py`：Gherkin + `requirement_ids`/`review_ids` | `testcases.json` |
| 8 | 校验评论→发现→需求→用例链路；无支持结论删除/修订/标假设 | `analysis/traceability.py`：确定性图遍历 + 修订 + 校验报告 | `traceability.json` 中检查逐条通过，含移除/假设/拦截记录 |
| 9 | UI 展示进度、阶段、中间结果、校验结果、错误、修订 | `app/static/app.js` 轮询 `/api/status`，进度列表 + 事件 | `progress.json` / UI 演示 |
| 10 | 展示中间与最终交付物（原始评论、清洗数据、分类、发现、PRD、用例） | 结果页 8 个 Tab + `/api/artifacts` | UI 各 Tab |

另外两条硬约束：

- 支持输入分析目标/约束（订阅转化、可用性、版本、低分评论）→ S0 范围解析 + UI 目标输入框。
- 无 app 专属硬编码 → 主题/发现/需求/用例全部由数据动态生成，测试覆盖「未见过的 App + 数据集」。

## 3. AI Requirements（模型要求）

| 评估书要求 | 项目实现 | 验证 |
| --- | --- | --- |
| 至少一个核心语义任务模型驱动 | LLM 承担：范围抽取、主题命名/归并、发现生成、需求生成、测试用例生成（5 个任务） | `docs/AI.md`；`summary.json` 的 `model_driven=true` |
| 规则/统计/模型分工明确并说明理由 | 规则承担采集/清洗/去重/规范化/校验；统计承担分布与样本数；模型承担语义综合，边界见 README.md「规则 / 统计 / 模型分工」 | README.md 对应章节 |
| 每条主要发现含来源评论 ID/摘录、样本数、置信度/不确定性、冲突证据 | `findings.json` 字段：`evidence_review_ids`/`sample_count`/`confidence`/`uncertainty`/`conflicts` | 查看发现 Tab |
| 模型结论与确定性统计可区分 | 每条发现带 `provenance`（`stat`/`model`），UI 用不同徽章 | 发现 Tab 徽章 |
| 文档化模型/供应商、主要 prompt、配置、失败处理、防幻觉 | `docs/AI.md` + `prompts.py` 集中管理全部提示词 | `docs/AI.md` |
| 密钥走环境变量、不入仓库 | `.env.example` 仅占位；`.gitignore` 排除 `.env` | `git ls-files | grep .env` 为空 |

## 4. Deliverables（交付物）

| 评估书要求 | 项目实现 | 验证 |
| --- | --- | --- |
| 提交 GitHub 项目链接且本地可运行 | `https://github.com/ggssss03/app-review-insights`，`python app/server.py` 零依赖启动 | 本地运行 + README |
| 完整源码、依赖配置、运行说明、采集方法说明、样例输出/缓存 | 源码 + `pyproject.toml`/`requirements.txt`（零依赖）+ README + `data/` 缓存 + `data/README.md` | README 快速开始 |
| 缓存结果明确标注，不替代处理未见输入的能力 | 缓存带 `fetched_at`/`url` 信封；导入与采集接口始终可用 | `collection_notes.json`；`tests/test_scenarios.py` |
| 支持导入文档化的 JSON/CSV 格式 | `importer.py` + Web 上传入口 + 字段别名表（README） | `tests/test_importer.py`、`tests/test_app.py` |
| 换链接/数据集/目标仍能有依据地产出 | 全动态分类与生成；场景测试覆盖混合语言/证据不足/模型失败/重复冲突 | `tests/test_scenarios.py` |
| 完整 commit 历史体现迭代与 vibe coding | 40+ 次提交，从 M0 骨架到 P3 交付 | `git log --oneline` |

## 5. Technical Requirements and Notes（技术要求）

| 评估书要求 | 项目实现 | 验证 |
| --- | --- | --- |
| 技术栈不限 | Python 3.10+ 纯标准库后端 + 原生 HTML/CSS/JS 前端（刻意零依赖，便于评审环境直接运行） | `requirements.txt` 无运行时依赖 |
| 可用公共 API/采集库，但须说明数据源与限制 | 仅用 Apple Lookup 与 WebObjects 官方接口；限制写入 `collection_notes.json` 与 README | README 数据来源节 |
| 注意限速，不给目标站点异常负载 | 请求间隔 ≥ 1 秒 + 断点续采 + 缓存 | `collector.py` |
| 提供示例环境文件，不含密钥 | `.env.example` 只有占位 | `.env.example` |
| 不接受只写文档不可运行的提交 | 全流程可执行 + 76 个测试 + `self_check.py` | `python scripts/self_check.py` |

## 6. Evaluation Criteria（评分标准）

| 评分点 | 项目实现 | 验证 |
| --- | --- | --- |
| 数据真实可复现、来源与限制清晰 | 官方接口 + 信封缓存 + 采集说明 + 诚实声明限制 | `data/README.md`、`collection_notes.json` |
| 清洗/分类/分析合理，能暴露真实用户问题 | 规则清洗 + 动态聚类 + 带证据发现；订阅目标能产出定价/付费墙相关发现与需求 | `findings.json`、`requirements.json` |
| 模型语义分析超越规则并能泛化 | LLM 主题命名/发现/PRD/用例；无硬编码；未见数据 E2E 场景测试 | `tests/test_scenarios.py` |
| 发现区分证据/统计/模型/不确定性/冲突 | `provenance`、`confidence`、`uncertainty`、`conflicts` 字段 + UI 徽章 | 发现 Tab |
| PRD 有依据、边界清晰、分优先级与版本 | 需求链接 finding/review，P0–P2、V1/V2、验收标准 | 需求 Tab |
| 测试覆盖 PRD 且可追溯回评论 | Gherkin 用例链接需求与评论，S7 校验通过 | 用例/溯源 Tab |
| UI 清晰、本地可运行、交付说明清楚 | 亮色全息 UI + 零依赖启动 + README/PLAN/EVALUATION 三文档 | `python app/server.py` |

## 7. Important Notes（重要说明）

| 评估书要求 | 项目实现 |
| --- | --- |
| 不只是爬虫，也不只是 UI；核心是把评论转化为可执行需求与测试计划 | S4–S7 完成问题发现 → 需求 → 用例 → 校验的闭环 |
| 不爬页面可见内容，用更合适的方式获取评论 | 只用 Apple 官方 Lookup / WebObjects 公共接口，不解析页面评论 |
| PRD 需求必须可追溯到具体评论 | 需求 `review_ids` 自动回填并校验 |
| 测试用例能验证需求是否解决评论中的问题 | Gherkin 用例链接需求与来源评论 |
| 用 AI 编码助手不等于满足 AI 要求 | 运行时模型驱动：S0/S3/S4/S5/S6 均实时调用 LLM |
| 能应对未见数据、混合语言、重复冲突、证据不足、采集/模型失败 | `tests/test_scenarios.py` 覆盖四类场景；降级策略见 `docs/AI.md` |
| 数据不足时如实说明，不编造 | 低置信折叠、样本边界声明、空数据明确报错 |

## 8. 本地验证命令

```bash
PYTHONPATH=src python -m unittest discover -s tests -v   # 76 个用例
python scripts/self_check.py                              # 一键自检
python app/server.py --port 8765                         # 启动 UI
```
