# App Review Insights — 实施计划书

目标来源：https://github.com/retro-labs/app-review-insights/blob/main/README.md
项目根目录：`D:\Users\Administrator\Documents\agent_demo`

---

## 1. 目标理解（README → 可验收要求）

README 的核心目标：**做一个可运行的 App Store 评论分析工具**——用户输入美国区 App Store 链接 + 分析目标/约束，点击 Start 后系统自动完成「采集 → 清洗 → 动态分类 → 证据评估 → 版本规划/PRD → 测试用例 → 追溯校验」全流程，并在 UI 里展示进度与所有中间/最终交付物。所有结论必须能追溯到具体用户评论，且不能依赖任何 app 专属的硬编码。

可验收要求清单：

| 编号 | 要求 | 验收证据 |
| --- | --- | --- |
| R1 | 可运行工具/Web 应用，输入美国区 App Store 链接 + 目标/约束，点击 Start 自动跑完整工作流 | 本地 `uv run` 可启动，端到端跑通示例 app |
| R2 | 不依赖 app 专属硬编码的分类、发现、需求、测试 | 换一个未见过的 app/数据集仍能产出 |
| R3 | 完整工作流：范围 → 采集 → 清洗去重 → 动态分类 → 证据评估 → 版本规划/PRD → 测试用例 → 追溯校验 | 每个阶段有中间产物和校验结果 |
| R4 | 至少一个核心语义任务由模型驱动（动态主题发现/问题归并/证据分析/需求生成/测试生成） | 代码中有 LLM 调用 + 运行时真实生效 |
| R5 | 规则/统计/模型分工明确，并解释每阶段选择理由 | ARCHITECTURE.md / README 说明 |
| R6 | 每条主要发现含：来源 review ID/摘录、样本数、置信度/不确定性、冲突证据；模型结论与统计结论可区分 | 发现对象字段 + UI 徽章 |
| R7 | 文档化模型/供应商、主要 prompt、模型配置、失败处理、防幻觉措施 | docs/ 下专项文档 |
| R8 | 密钥走环境变量，不提交仓库 | .env.example 无真实密钥，git 无密钥 |
| R9 | GitHub 项目、本地可运行、源码/依赖/运行说明/采集方法说明/样例输出或缓存数据 | README + data/ 目录 |
| R10 | 支持 JSON/CSV 导入；未见过的 app/数据集/目标也能有依据地产出 | 导入入口 + 换数据 E2E 测试 |
| R11 | 完整 commit 历史体现迭代与 vibe coding 过程 | GitHub 提交记录 |

---

## 2. 总体架构

```text
用户
 │  输入 App Store URL + 分析目标/约束（或导入 JSON/CSV）
 ▼
UI（React SPA；MVP 阶段用 Streamlit）
 │  SSE 进度 / 阶段中间结果 / 最终交付物
 ▼
FastAPI 后端（REST + SSE + Pydantic）
 ▼
流水线编排器（阶段状态机，可断点续跑，每阶段结果缓存）
 ├─ S0 范围解析
 ├─ S1 数据采集（Apple Lookup + Customer Reviews RSS；或本地导入）
 ├─ S2 清洗 / 去重 / 结构化
 ├─ S3 动态分类（embedding + 聚类 + LLM 命名归并）
 ├─ S4 证据评估（充分性 / 冲突 / 不确定性）
 ├─ S5 版本规划 + PRD
 ├─ S6 测试用例生成
 ├─ S7 追溯校验
 └─ S8 汇总输出
存储：SQLite（apps / runs / reviews / topics / findings / requirements / test_cases / traceability）
模型：LLM 适配器（OpenAI 兼容：DeepSeek / OpenAI / Qwen / Ollama）+ 本地多语言 embedding
```

设计原则：本地可运行优先、模型供应商无关、全流程可审计、无 app 硬编码。

---

## 3. 技术选型

| 层 | 推荐 | 理由 | 备选 |
| --- | --- | --- | --- |
| 语言/运行时 | Python 3.12 | 数据分析 + LLM 编排生态最好，异步支持好 | Node.js/TypeScript |
| Web 后端 | FastAPI + uvicorn | 原生 async、Pydantic 校验、SSE 进度推送 | Flask / Next.js API |
| 前端 | React 18 + Vite + TS + Tailwind/shadcn | 工作流进度、表格、追溯视图可控可定制 | Streamlit（MVP）、Vue |
| 数据存储 | SQLite + SQLAlchemy | 零配置、单文件、可复制可审查、规模够用 | DuckDB / Postgres |
| 数据采集 | httpx + Apple Lookup API + Customer Reviews RSS（US） | 官方公共接口、无需爬页面；RSS 为 README 认可的“更合适方式” | 第三方采集库、手动导入 |
| 数据处理 | Polars（或 pandas） | 列式、快；清洗/去重用确定性规则 | pandas |
| 嵌入模型 | sentence-transformers 多语言模型（本地） | 免费、可复现、支持中英混合评论 | OpenAI embeddings |
| 聚类 | HDBSCAN（或 KMeans + 轮廓系数选 k） | 动态主题发现，无需预定义分类数/主题 | BERTopic |
| LLM | OpenAI 兼容适配器，默认 DeepSeek，可切 OpenAI/Qwen/Ollama | 便宜、中英混合好、防厂商锁定、本地可跑 | Claude / Gemini |
| 结构化输出 | Pydantic + JSON Schema + function calling | 强制字段、降低幻觉、失败可重试 | 纯文本解析 |
| 测试 | pytest + pytest-asyncio + fixtures；Playwright E2E | 规则层可单测，E2E 覆盖“换新输入”场景 | — |
| CI/采集 | GitHub Actions（lint/test + 定时 US runner 采集） | 解决国内网络 RSS 为空的问题，同时满足“可复现数据” | — |
| 图表 | Recharts / ECharts | 评分分布、主题占比、时间趋势 | 内置图表（Streamlit） |

### 每层为什么这么选（README R5 要求）

- **采集**用确定性规则（官方 RSS + 分页 + 限速 + 缓存）：数据真实性优先，规则可复现、可控限流。
- **清洗/去重/规范化**用确定性规则：结果稳定、可审计，不需要模型判断的部分绝不浪费模型。
- **主题发现与归并**用「本地 embedding + 聚类 + LLM 命名」：聚类保证动态、无硬编码分类；LLM 负责把簇翻译成人类可读的主题并归并相近主题。
- **发现生成 / PRD / 版本拆分 / 测试生成**用 LLM：这些是语义综合任务，规则做不了。
- **证据充分性、冲突检测、追溯校验**用统计 + 确定性图遍历为主，LLM 辅助判断语义冲突。

---

## 4. 数据采集与数据源

### 主链路（官方公共接口）

1. **应用元数据**：`https://itunes.apple.com/lookup?id=<app_id>&country=us`
   - 已验证：示例 app `839285684`（Workout for Women: Home & Gym）返回名称、分类 Health & Fitness、53 万+ 评分、均分 4.85、最新版本日期等。
2. **评论数据**：`https://itunes.apple.com/us/rss/customerreviews/id=<app_id>/sortBy=mostRecent/json`
   - `page=1..10`，每页最多 50 条；`sortBy=mostRecent` 与 `sortBy=mostHelpful` 两种排序，合计最多约 1000 条。
   - 请求间隔 ≥ 1 秒，原始响应落盘缓存，支持断点续采。

### 已实测的坑（重要）

当前网络（国内）下，美国区评论 RSS 对任意应用都返回**空 feed**（连 WhatsApp `310633997` 也空）；应用元数据接口正常。判断为苹果对地区/网络的限制，而非应用问题。对策：

1. **GitHub Actions 定时采集**：用 US runner 每周采集示例 app（及配置列表）评论，把原始 JSON 提交到 `data/raw/`，标注 `fetched_at`、来源 URL、storefront。
2. **导入入口（README 硬性要求 R10）**：应用支持导入合规 JSON/CSV 评论数据集，作为离线评审和“未见数据”测试的主要通道。
3. **采集脚本保留本地直连能力**：在可直连的网络（如 US 代理/海外机器）上直接运行即可刷新数据。

### 数据合规与边界

- 只用公共接口数据，不爬页面可见内容（README 明确不建议）。
- 每条数据记录来源与抓取时间；缓存数据明确标注「离线缓存，仅供评审」，不冒充实时采集。
- 数据不足时如实展示，绝不编造评论。

---

## 5. 分析流水线（九阶段）

| 阶段 | 输入 | 方法（规则/统计/模型） | 输出 | 校验点 |
| --- | --- | --- | --- | --- |
| S0 范围解析 | 用户目标/约束文本 | LLM 结构化抽取 + 规则校验 | `scope_json`（分析维度、版本/评分过滤、重点） | 非法值回退为默认全量 |
| S1 采集/导入 | App URL 或 JSON/CSV | 规则：RSS 分页、限速、缓存；导入解析 | `reviews_raw` + 元数据 | 来源可溯、数量与限制说明 |
| S2 清洗去重 | 原始评论 | 规则：字段规范化、按 review id/内容哈希去重、语言检测、垃圾过滤、PII 脱敏 | `reviews_clean` | 去重率、过滤率统计 |
| S3 动态分类 | 清洗后评论 | embedding + HDBSCAN 聚类；LLM 命名/归并主题；逐条归类（最近簇或 LLM）+ 置信度 | `topics` + 成员关系 | 簇可解释、无固定分类表 |
| S4 证据评估 | 主题与评论 | 统计（样本数/分布/一致性）+ LLM（语义冲突、不确定性） | `findings`（含证据、置信度、冲突） | 每条 finding 有 ≥1 review 引用 |
| S5 版本规划 + PRD | findings | LLM 生成需求（编号/优先级/版本归属/验收标准）+ 规则校验 | `requirements` | 需求可追溯到 finding/review |
| S6 测试用例 | requirements | LLM 生成 Gherkin 用例 + 规则校验 | `test_cases` | 用例链接需求与评论 |
| S7 追溯校验 | 全链路对象 | 确定性图遍历 + LLM 辅助修订建议 | `validation_report` | 孤立结论删除/修订/标 assumption |
| S8 汇总输出 | 各阶段产物 | 规则组装 | 汇总报告 + 交付物 JSON | 限制与不确定性明示 |

---

## 6. 数据模型（SQLite）

核心表（字段可随实现微调，但追溯链路字段必须保留）：

```text
apps(id, app_id, name, storefront, url, metadata_json, fetched_at)
runs(id, app_id, goal_text, scope_json, status, created_at)
reviews_raw(id, run_id, source, page_url, raw_json, fetched_at)
reviews_clean(id, run_id, raw_id, dedup_key, rating, title, body, lang,
              version, country, is_junk, normalized_json)
topics(id, run_id, label, description, method, model, embedding_model)
review_topic_memberships(review_id, topic_id, score, confidence, method)
findings(id, run_id, code, statement, evidence_review_ids, sample_count,
         confidence, conflicts_json, provenance(rule|stat|model),
         status(kept|assumption|removed), rationale)
requirements(id, run_id, code, title, description, priority,
             planned_version, finding_ids, review_ids, acceptance_criteria)
test_cases(id, run_id, code, gherkin_json, requirement_ids, review_ids)
validation_report(run_id, checks_json, removed_ids, revised_ids, assumption_ids)
```

`provenance` 字段保证「模型结论 vs 确定性统计」永远可区分（README R6）。

---

## 7. 模型驱动与防幻觉设计

### 模型承担（README R4，至少一项为运行时模型驱动）

- 范围解析（从自由文本目标提取分析维度）
- 动态主题命名与归并
- 评论归类（必要时，低置信度时回退最近簇）
- 发现生成（只基于给定评论证据）
- 冲突与不确定性判断
- 需求生成 / 版本拆分 / PRD 撰写
- 测试用例生成

### 规则承担

- 采集、分页、限速、缓存
- 去重、字段规范化、语言检测、垃圾过滤、PII 脱敏
- 评分/版本/时间分布等统计
- 追溯图遍历校验、ID 引用校验

### 防幻觉措施（逐条落地到代码）

1. **引用白名单**：LLM 只能引用输入给它的 `review_id`，输出后用集合校验，非法引用直接拒绝并重试/修正。
2. **结构化输出**：Pydantic + JSON Schema 强校验，失败自动重试（最多 2 次）。
3. **低温度 + few-shot**：生成类任务 temperature ≤ 0.3，带 1-2 个示例。
4. **二次核验 pass**：生成发现后，再用模型对照引用评论核验；证据不足 → 删除或标 `assumption`。
5. **置信度/不确定性必填**：`confidence`、`conflicts_json` 字段非空；UI 展示。
6. **故障降级**：模型超时/不可用时，输出确定性统计结果并在 UI 标注「模型未参与」，流程不阻塞。
7. **密钥管理**：`.env.example` 只给占位；`LLM_PROVIDER` / `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` 等全部环境变量注入。

### 需要文档化的内容（README R7）

- 使用的模型与供应商（默认 DeepSeek，可切换）
- 每个模型任务的主要 prompt / tool definition
- 模型参数配置（温度、max_tokens、重试策略）
- 失败处理策略
- 防幻觉与证据约束说明

---

## 8. 可追溯性设计

- 统一 ID 体系：`review_id → finding → requirement → test_case`。
- UI 提供「追溯视图」：点任意需求 → 看到来源 finding → 看到原始评论摘录；反向可查。
- 确定性校验规则：
  - 每条 finding 必须引用 ≥1 个存在的 review_id；
  - 每条 requirement 必须有 finding/review 支持；
  - 每个 test_case 必须链接 requirement 且能定位到 review；
  - 无支持的结论：删除，或标记 `assumption` 并在 UI/导出中可见。
- 校验报告输出：检查项、通过/失败、修订记录（删除/修订/标注假设各几条）。

---

## 9. UI 设计

- **首页**：App Store URL 输入 + 分析目标/约束（快捷选项 + 自由文本）+ 导入 JSON/CSV + Start。
- **运行页**：九阶段时间线（状态/耗时/日志/错误/重试），每阶段中间结果可展开。
- **交付物页**：Tab——原始评论 / 清洗后数据 / 主题与分类 / 发现（含证据与置信度）/ PRD（分版本）/ 测试用例 / 追溯视图 / 校验报告。
- **标记约定**：`规则统计` / `模型生成` / `假设(assumption)` / `已移除` 用不同徽章或颜色区分。
- **异常态**：数据为空、数据量过小、模型失败时明确提示，不假装成功。

---

## 10. 里程碑（层层递进，建议不跳步）

### M0 基建（0.5–1 天）
- 初始化 git 仓库、Python 环境（uv/venv）、目录骨架、`.env.example`、README 初稿、CI 占位。
- **验收**：`pytest` 有最小用例通过；项目结构清晰。

### M1 数据层（1 天）
- 采集脚本（Lookup + RSS，US 区、分页、限速、缓存）；JSON/CSV 导入器；清洗/去重/规范化。
- **验收**：示例 app 产出真实 `reviews_clean`（直连或导入数据集跑通），数据来源与限制写进文档。

### M2 分析层（1–2 天）
- embedding + 聚类 + LLM 主题命名/归并；逐条归类与置信度；统计与模型发现；证据评估。
- **验收**：换未见过的 app 数据集，仍能产出动态主题与带证据的发现。

### M3 规划层（1–2 天）
- 需求生成、优先级、版本拆分（V1/V2）、PRD；测试用例；追溯校验。
- **验收**：需求→测试全链路可追溯；孤立结论被处理；校验报告生成。

### M4 应用层（1–2 天）
- 已交付：纯标准库 Web 服务器 + 原生 JS 前端（`app/server.py` + `app/static/`），
  进度轮询、交付物 Tab、JSON/CSV 导入、统计/模型/假设徽章区分。
- 可选升级：FastAPI + SSE + React（不影响 README 验收，仅在需要更强扩展性时做）。
- **验收**：输入链接+目标 → Start → 全流程可视化跑完。

### M5 交付加固（1 天）
- E2E 验证：新链接 / 新数据集 / 混合语言 / 重复冲突 / 证据不足 / 模型故障。
- 文档完善（README / ARCHITECTURE / EVALUATION）；提交历史整理；推 GitHub。
- **验收**：README 自检清单逐项对照通过。

---

## 11. 风险与对策

| 风险 | 对策 |
| --- | --- |
| 国内网络 RSS 评论为空 | GitHub Actions US runner 定时采集 + 缓存入库 + JSON/CSV 导入兜底（已实测确认） |
| RSS 覆盖有限（约 1000 条） | 两种排序合并、明确限制说明、导入扩展数据量 |
| LLM 幻觉/无依据结论 | 引用白名单 + 结构化输出 + 二次核验 + assumption 标记 |
| 数据量太少 | 如实展示证据不足，不编造 |
| 评论混合中英语言 | 多语言 embedding + 多语言提示词 |
| 评审换 app/数据集 | 全动态分类、无硬编码分类/需求/测试 |
| 密钥泄露 | .env 不入库、示例无真实 key、CI 用 secrets |
| 模型服务故障 | 重试 + 降级到确定性统计 + UI 明确标注 |

---

## 12. 与评估标准对照

| README 评估点 | 落地设计 | 验证位置 |
| --- | --- | --- |
| 数据真实可复现、来源清晰 | 官方 RSS + 缓存标注 + 文档 | data/README + 采集脚本 |
| 清洗/分类/分析合理、暴露真实问题 | 规则清洗 + 动态主题 + 发现证据字段 | S2–S4 + 交付物页 |
| 模型驱动超越规则、能泛化 | LLM 主题命名/发现/PRD/测试 + 无硬编码 | 换数据 E2E 测试 |
| 区分证据/统计/模型/不确定性/冲突 | `provenance`、`confidence`、`conflicts` 字段 | 发现对象 + UI 徽章 |
| PRD 有依据、边界清晰、分版本 | 需求链接 finding/review、P0–P2、V1/V2 | S5 + 追溯视图 |
| 测试覆盖 PRD 且可追溯 | Gherkin 用例链接需求与评论 | S6 + 追溯校验报告 |
| UI 清晰、本地可运行 | 阶段时间线 + 交付物 Tab + 运行文档 | README + M4/M5 验收 |

---

## 13. 第一步怎么做（立刻可执行）

**第一步：搭好仓库骨架并打通「数据采集/导入」这一环。** 后面的所有分析都依赖真实、可复现的评论数据，所以先解决数据，再做模型与分析。

1. 初始化 git 仓库和 Python 环境：
   - `git init`（用本机 bundled git：`C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe`）
   - 建 `backend/`、`frontend/`（或 `app/`）、`scripts/`、`data/`、`docs/`、`.env.example`、`README.md`
   - 建虚拟环境并安装依赖（httpx、polars、pydantic、sentence-transformers、fastapi、uvicorn、pytest）
2. 写 `scripts/fetch_reviews.py`：
   - Lookup 拿应用元数据 → `data/raw/<app_id>/app.json`
   - RSS 按 `page=1..10`、`sortBy=mostRecent` 与 `mostHelpful` 采集 → `data/raw/<app_id>/reviews-*.json`
   - 请求间隔 ≥1s，断点续采（已抓页面跳过）
3. 因为当前网络 RSS 为空：在仓库里配好 GitHub Actions 采集工作流（us-latest runner），把首批真实评论拉下来提交进 `data/raw/`；同时把「导入 JSON/CSV」的入口函数写好，先用一份符合格式的样例数据把清洗链路跑通。
4. 提交第一次 commit，验收标准：
   - `data/raw/839285684/` 下有带 `fetched_at` 和来源 URL 的真实评论文件（或导入的数据集）；
   - `pytest` 通过（采集解析、导入、去重的最小用例）；
   - `README.md` 写清楚数据来源与限制。

完成这一步后，M1 数据层的验收即达成，可以进入 M2 分析层。
