# AI / 模型设计文档（README R7 对应项）

## 1. 模型与供应商

本项目的模型层是 **OpenAI 兼容 Chat Completions 适配器**（`src/app_review_insights/llm.py`），
可通过环境变量切换到任意兼容服务：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LLM_PROVIDER` | `deepseek` | 供应商名称（仅用于展示/日志） |
| `LLM_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容 base URL |
| `LLM_API_KEY` | （空） | 密钥，仅从环境变量/.env 读取 |
| `LLM_MODEL` | `deepseek-v4-flash` | 模型名 |
| `LLM_TEMPERATURE` | `0.3` | 生成类任务温度（低温度降低幻觉） |
| `LLM_TIMEOUT` | `60` | 单次请求超时（秒） |
| `LLM_MAX_RETRIES` | `2` | 失败重试次数 |

当前实测可兼容：DeepSeek、OpenAI、Qwen（DashScope 兼容模式）、Ollama 本地服务。
复制 `.env.example` 为 `.env` 并填写 `LLM_API_KEY` 即可启用。

## 2. 各任务使用的模型与提示词

所有提示词集中在 `src/app_review_insights/prompts.py`，任务清单：

| 任务 | 触发阶段 | 输出 | 说明 |
| --- | --- | --- | --- |
| 范围解析 | S0 | `scope` JSON | 从用户目标/约束抽取分析维度、星级/版本过滤 |
| 主题命名/归并 | S3 | `topics` JSON | 给聚类命名并归并，是「动态主题发现」的模型驱动核心 |
| 发现生成 | S4 | `findings` JSON | 只允许引用输入评论的 review_id |
| 需求/版本规划 | S5 | `requirements` JSON | 生成 PRD 需求、优先级 P0-P2、版本 V1/V2 |
| 测试用例 | S6 | `test_cases` JSON | Gherkin 格式，链接需求与评论 |

每个任务都带系统级硬性规则：只允许引用白名单内 ID、证据不足必须降低置信度、
冲突必须显式列出、输出必须是合法 JSON。

## 3. 模型配置与防幻觉措施

1. **引用白名单**：模型只能引用输入给它的 `review_id`；代码在输出后做集合校验，
   非法引用直接丢弃，绝不进入交付物。
2. **结构化输出**：所有模型任务要求 JSON 对象，代码用 `parse_json_content` + 字段校验，
   失败自动重试（最多 2 次）。
3. **低温度**：默认 0.3。
4. **置信度/不确定性/冲突字段必填**：`confidence` 会被钳制到 0-1；
   `uncertainty`、`conflicts` 进入最终交付物，UI 必须展示。
5. **统计与模型结论可区分**：每条发现带 `provenance`（`stat` / `model`）。
6. **追溯校验兜底**：S7 确定性图遍历会把无有效评论引用的发现删除、
   无支持的需求标记为 `assumption`、悬空测试用例删除，并输出校验报告。

## 4. 失败处理策略

- **网络/鉴权/限流**：指数退避重试（429/5xx）；401/403 直接报错提示检查 key。
- **解析失败/空内容**：容忍 markdown 围栏与前后噪声；空内容或非法 JSON 自动重试（最多 2 次）。
- **模型不可用**：流水线降级为确定性模式——主题用「主题 N」占位命名，
  发现只保留统计发现，需求/测试明确标注「未生成：需要 LLM 配置」；
  任何模型失败都会写入交付物与进度事件，绝不静默伪装成功。
- **断点续跑**：每个阶段结果缓存在 `data/processed/<app_id>/analysis/`，
  失败后可修复配置后重跑，已成功的阶段直接复用（`--force` 强制重算）。

## 5. 无硬编码承诺

- 主题数量与名称完全由「嵌入 + 聚类 + LLM 命名」动态决定，不预设分类表。
- 需求与测试用例由 LLM 依据当前 app 的发现生成，不携带任何 app 专属模板。
- 规则层（采集/去重/规范化/统计/追溯校验）与模型层职责边界见 `PLAN.md` 第 7 节。
