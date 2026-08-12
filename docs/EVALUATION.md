# 评估标准自检（README Evaluation Criteria 逐项对照）

目标文档：https://github.com/retro-labs/app-review-insights/blob/main/README.md

| README 评估点 | 实现位置 | 验证方式 |
| --- | --- | --- |
| 数据真实可复现、来源清晰、说明限制 | `scripts/fetch_reviews.py`、`data/README.md`、缓存信封（url/fetched_at） | 检查 `data/raw/<id>/` 文件；运行采集脚本 |
| 清洗/分类/分析合理、暴露真实问题 | `cleaner.py`（去重/垃圾/PII/语言）、`analysis/topics.py`、`analysis/findings.py` | `python scripts/clean_reviews.py <id>`；查看 findings |
| 模型驱动超越规则、可泛化到未见数据 | LLM 承担主题命名、发现、需求、测试；无 app 硬编码分类表 | 换未见过 app/数据集跑 `scripts/analyze.py`；`docs/AI.md` |
| 区分证据/统计/模型/不确定性/冲突 | `provenance`、`confidence`、`uncertainty`、`conflicts` 字段 + UI 徽章 | 查看 findings JSON 或 Web UI「发现」Tab |
| PRD 有依据、边界清晰、分版本 | `analysis/planning.py`：需求链接 finding/review，P0-P2，V1/V2 | Web UI「需求(PRD)」Tab；`data/processed/<id>/analysis/requirements.json` |
| 测试覆盖 PRD 且可追溯 | `analysis/planning.py` 生成 Gherkin，链接需求与评论 | Web UI「测试用例」Tab；追溯校验报告 |
| UI 清晰、本地可运行 | `app/server.py` + `app/static/`（纯标准库） | `python app/server.py` 后打开 http://127.0.0.1:8765 |
| 支持 JSON/CSV 导入 | `importer.py` + Web 上传入口 | `tests/test_app.py`（导入→分析→产物） |
| 失败/数据不足时诚实展示 | 确定性降级、assumption/removed 标记、空数据如实报错 | `tests/test_scenarios.py`（模型失败、证据不足、混合语言、重复冲突） |
| 密钥不入库 | `.env.example` 仅占位，`.gitignore` 排除 `.env` | `git ls-files | grep .env` 为空 |
| 完整 commit 历史体现迭代 | 仓库 main 分支多次提交 | `git log --oneline` |

## 本地自检命令

```bash
PYTHONPATH=src python -m unittest discover -s tests -v   # 50+ 用例
python scripts/self_check.py                              # 一键自检 + 离线演示
python app/server.py --port 8765                         # 启动 UI
```

## 已知限制（如实声明）

1. 采集按链接国家取数（默认中国区）：cn RSS 间歇可用（自动重试），
   与产品页内嵌评论、美国区 itml 批次多源合并，去重后通常 35+ 条。
2. cn RSS 单页约 35 条、不提供分页/排序翻页，且间歇返回空 feed；
   采集器自动重试并在 RSS 为空时用产品页 + 美国区批次补充，报告中会说明样本边界。
3. 未配置 `LLM_API_KEY` 时运行确定性模式：主题占位命名、仅统计发现、
   需求/测试明确标注未生成；配置后自动启用模型驱动（本仓库已用 DeepSeek 端到端验证）。
