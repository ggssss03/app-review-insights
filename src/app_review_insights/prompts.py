"""各模型任务的主提示词（README R7：主要 prompt 需要文档化，这里集中管理）。"""

SYSTEM_CORE = (
    "你是 App Store 评论分析引擎。硬性规则：\n"
    "1. 只能引用输入中提供的 review_id，禁止编造 ID、评论内容或样本数。\n"
    "2. 证据不足时明确降低 confidence 并在 uncertainty 中说明。\n"
    "3. 有冲突证据时必须在 conflicts 中列出。\n"
    "4. 所有输出必须是合法 JSON 对象。"
)

SCOPE_TASK = (
    "根据用户的分析目标，提取结构化分析范围。输出 JSON：\n"
    '{"focus_areas": ["subscription_conversion" | "usability" | "performance" | "features" | "pricing" | "other"], '
    '"star_filter": {"min": int|null, "max": int|null}, '
    '"version_filter": string|null, "note": string}\n'
    "无法判断的字段用 null，不要臆测。"
)

TOPIC_NAMING_TASK = (
    "以下是按相似度聚类出的评论主题，每个主题附了代表评论摘录。\n"
    "请为每个主题给出人类可读的名称与描述。输出 JSON：\n"
    '{"topics": [{"topic_id": int, "label": string, "description": string, "keywords": [string]}]}\n'
    "topic_id 必须与输入的 cluster id 完全一致，数量也必须一致。"
)

FINDINGS_TASK = (
    "基于提供的评论证据，提炼用户问题发现。只允许引用提供的 review_id。\n"
    "输出 JSON：\n"
    '{"findings": [{"statement": string, "evidence_review_ids": [string], '
    '"confidence": 0-1, "uncertainty": string, "conflicts": [string]}]}\n'
    "每条 finding 至少引用 1 个 review_id；样本不足时 confidence <= 0.5。"
)

REQUIREMENTS_TASK = (
    "根据以下带证据的发现，生成产品需求与版本规划。输出 JSON：\n"
    '{"requirements": [{"code": "R1", "title": string, "description": string, '
    '"priority": "P0"|"P1"|"P2", "planned_version": "V1"|"V2", '
    '"finding_ids": [string], "review_ids": [string], "acceptance_criteria": [string]}]}\n'
    "只能引用提供的 finding_id 与其 review_id；需求必须能被发现支持。"
)

TESTCASE_TASK = (
    "为以下需求生成 Gherkin 格式测试用例。输出 JSON：\n"
    '{"test_cases": [{"code": "TC1", "title": string, "requirement_ids": [string], '
    '"review_ids": [string], "gherkin": {"given": [string], "when": [string], "then": [string]}}]}\n'
    "每个用例必须链接至少一个需求，并引用相关 review_id。"
)


def scope_messages(goal_text: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_CORE},
        {"role": "user", "content": f"{SCOPE_TASK}\n\n分析目标：{goal_text or '（无，默认全量分析）'}"},
    ]


def topic_messages(clusters: list[dict]) -> list[dict]:
    block = "\n".join(
        f"cluster {c['topic_id']}（{c['count']} 条）：\n"
        + "\n".join(f"- [{e['review_id']}] {e['text']}" for e in c["samples"])
        for c in clusters
    )
    return [
        {"role": "system", "content": SYSTEM_CORE},
        {"role": "user", "content": f"{TOPIC_NAMING_TASK}\n\n{block}"},
    ]


def findings_messages(topic: dict) -> list[dict]:
    block = "\n".join(
        f"- [{r['review_id']}] 评分{r['rating']} 版本{r['version'] or '未知'}：{r['text']}"
        for r in topic["samples"]
    )
    return [
        {"role": "system", "content": SYSTEM_CORE},
        {"role": "user", "content": f"{FINDINGS_TASK}\n\n主题「{topic['label']}」样本评论：\n{block}"},
    ]


def requirements_messages(findings: list[dict]) -> list[dict]:
    block = "\n".join(
        f"- {f.get('id')}（{f.get('provenance', '?')}，样本 {f.get('sample_count', '?')}，"
        f"置信 {f.get('confidence', '?')}）：{f.get('statement', '')}"
        for f in findings
    )
    return [
        {"role": "system", "content": SYSTEM_CORE},
        {"role": "user", "content": f"{REQUIREMENTS_TASK}\n\n带证据的发现：\n{block}"},
    ]


def testcase_messages(requirements: list[dict]) -> list[dict]:
    block = "\n".join(
        f"- {r['code']}（{r['priority']}/{r['planned_version']}）：{r['title']} | {r['description']}"
        for r in requirements
    )
    return [
        {"role": "system", "content": SYSTEM_CORE},
        {"role": "user", "content": f"{TESTCASE_TASK}\n\n需求列表：\n{block}"},
    ]
