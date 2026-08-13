"""S5 版本规划/PRD 与 S6 测试用例生成（模型驱动 + 引用校验）。"""

from __future__ import annotations

from typing import Optional


def _valid_review_ids(findings: list[dict]) -> set[str]:
    ids: set[str] = set()
    for f in findings:
        ids.update(f.get("evidence_review_ids", []))
    return ids


def generate_requirements(
    findings: list[dict],
    llm: Optional[object] = None,
    *,
    focus_areas: Optional[list[str]] = None,
) -> tuple[list[dict], str]:
    """根据发现生成需求与版本规划；LLM 不可用时返回空并说明。"""
    supported = [f for f in findings if f.get("status") == "kept" and f.get("evidence_review_ids")]
    if llm is None or not supported:
        return [], "未生成需求：需要 LLM 配置（或没有可支持的发现）。"
    allowed_findings = {f["id"] for f in supported}
    allowed_reviews = _valid_review_ids(supported)
    try:
        from ..prompts import requirements_messages

        result = llm.chat_json(requirements_messages(supported, focus_areas))
        requirements = []
        for item in (result.get("requirements") or []):
            if not isinstance(item, dict):
                continue
            finding_ids = [str(i) for i in (item.get("finding_ids") or [])]
            review_ids = [str(i) for i in (item.get("review_ids") or [])]
            finding_ids = [i for i in finding_ids if i in allowed_findings]
            review_ids = [i for i in review_ids if i in allowed_reviews]
            if not finding_ids and not review_ids:
                continue
            requirements.append({
                "code": str(item.get("code") or f"R{len(requirements) + 1}")[:10],
                "title": str(item.get("title") or "").strip(),
                "description": str(item.get("description") or "").strip(),
                "priority": str(item.get("priority") or "P1"),
                "planned_version": str(item.get("planned_version") or "V1"),
                "finding_ids": finding_ids,
                "review_ids": review_ids,
                "acceptance_criteria": [str(a) for a in (item.get("acceptance_criteria") or [])],
                "status": "kept",
            })
        return requirements, "模型生成"
    except Exception as exc:  # noqa: BLE001
        return [], f"需求生成失败（{exc}），请检查 LLM 配置。"


def generate_test_cases(requirements: list[dict], llm: Optional[object] = None) -> tuple[list[dict], str]:
    """根据需求生成 Gherkin 测试用例。"""
    if llm is None or not requirements:
        return [], "未生成测试用例：需要 LLM 配置（或没有需求）。"
    allowed_requirements = {r["code"] for r in requirements}
    allowed_reviews = set()
    for r in requirements:
        allowed_reviews.update(r.get("review_ids", []))
    try:
        from ..prompts import testcase_messages

        result = llm.chat_json(testcase_messages(requirements))
        test_cases = []
        for item in (result.get("test_cases") or []):
            if not isinstance(item, dict):
                continue
            req_ids = [str(i) for i in (item.get("requirement_ids") or []) if str(i) in allowed_requirements]
            review_ids = [str(i) for i in (item.get("review_ids") or []) if str(i) in allowed_reviews]
            if not req_ids:
                continue
            gherkin = item.get("gherkin") or {}
            test_cases.append({
                "code": str(item.get("code") or f"TC{len(test_cases) + 1}")[:10],
                "title": str(item.get("title") or "").strip(),
                "requirement_ids": req_ids,
                "review_ids": review_ids,
                "gherkin": {
                    "given": [str(g) for g in (gherkin.get("given") or [])],
                    "when": [str(g) for g in (gherkin.get("when") or [])],
                    "then": [str(g) for g in (gherkin.get("then") or [])],
                },
            })
        return test_cases, "模型生成"
    except Exception as exc:  # noqa: BLE001
        return [], f"测试用例生成失败（{exc}），请检查 LLM 配置。"
