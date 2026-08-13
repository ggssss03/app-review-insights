# App Review Insights — 终极方案与交付说明

## 1. 目标

把真实 App Store 用户评论自动转化为**可追溯的产品需求（PRD）、版本规划和测试用例**，并通过零依赖 Web UI 完整展示
「采集 → 清洗 → 主题 → 发现 → 需求 → 用例 → 溯源校验」全流程。

评估要求核心：本次评估使用的评论数据必须来自**美国区 App Store storefront**。

## 2. 当前实现（S0–S8）

| 阶段 | 内容 | 实现 |
| --- | --- | --- |
| S0 | 范围解析 | 规则种子 + LLM 结构化抽取，失败回退全量 |
| S1 | 采集/导入 | 美区 itml 优先；JSON/CSV 导入兜底 |
| S2 | 清洗 | 去重、垃圾过滤、PII 脱敏、语言识别 |
| S3 | 主题 | TF-IDF/KMeans 聚类 + LLM 命名 |
| S4 | 发现 | 统计 + 模型发现，引用白名单、置信度、冲突 |
| S5 | 需求 | LLM 生成 PRD、优先级、版本拆分 |
| S6 | 用例 | Gherkin 测试用例，链接需求与评论 |
| S7 | 溯源 | 确定性图遍历校验，删除/标注假设，输出审计日志 |
| S8 | 汇总 | 汇总报告 + 交付物 + Web UI |

## 3. 数据策略（美区）

- 主样例 `839285684`（Workout for Women）使用美区 WebObjects `userReviewsRow` 官方接口。
- 该接口当前固定只返回 10 条热门评论，且不返回每条评论版本号；已如实标注限制，不编造。
- 分析输入最多保留 200 条；不足 200 条全量使用。
- 更丰富美区样本：需导入合规美区 JSON/CSV，或未来在可获取 AMP token 的美国区环境采集。

## 4. UI 与交互

- 亮色蓝粉全息主题（设计系统见 `design-system/app-review-insights/MASTER.md`）。
- 摘要：KPI、评分环形图、语言分布、分析范围、说明、运行模式、溯源校验。
- 主题：气泡图 + 关键词卡片。
- 发现：按置信度排序、低置信折叠、证据点击查看原文、追问/反例挑战。
- 需求：版本甘特、PRD 评审（接受/标记假设/删除 + 批注）。
- 用例：Gherkin 场景卡片。
- 溯源：SVG 全链路图 + 逐项检查 + 引用白名单拦截记录。
- 全局：S0–S8 侧栏导航、星级/语言/版本筛选、演示模式、Markdown/JSON 导出。

## 5. 模型与防幻觉

- OpenAI 兼容适配器，默认 DeepSeek，可切 OpenAI/Qwen/Ollama。
- 三道防线：引用白名单 + JSON 结构化校验/重试 + S7 确定性溯源兜底。
- 失败诚实降级到确定性模式，并在 UI/导出中标注。

## 6. 验证

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python scripts/self_check.py
python app/server.py --port 8765
```

- 75/75 单元/集成测试通过。
- `self_check.py` 全 PASS。

## 7. 已知限制

1. 美国区公开接口仅能自动获取 10 条热门评论；旧 RSS 已停用，AMP token 不可用。
2. 美区 itml 不返回每条评论版本号，版本筛选在当前样本无选项。
3. TF-IDF + KMeans 为离线轻量方案，可切换 sentence-transformers。
4. 数据量（百条级）使用 JSON 文件存储，暂未上数据库。
