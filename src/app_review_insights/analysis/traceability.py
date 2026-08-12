"""S7 追溯校验：确定性图遍历 + 修订（删除/标注假设），输出校验报告。"""

from __future__ import annotations


def validate_traceability(
    reviews: list[dict],
    findings: list[dict],
    requirements: list[dict],
    test_cases: list[dict],
) -> dict:
    """校验 评论 -> 发现 -> 需求 -> 测试 链路，并应用修订。"""
    review_ids = {r["review_key"] for r in reviews}
    checks: list[dict] = []
    removed_findings = []
    removed_tests = []
    assumption_requirements = []
    kept_findings = []
    kept_requirements = []
    kept_tests = []

    for f in findings:
        valid = [i for i in f.get("evidence_review_ids", []) if i in review_ids]
        if not valid:
            f["status"] = "removed"
            removed_findings.append(f["id"])
            checks.append({"check": "finding_evidence", "id": f["id"], "passed": False, "detail": "无有效评论引用，已移除"})
        else:
            f["evidence_review_ids"] = valid
            f["sample_count"] = len(valid)
            kept_findings.append(f)
            checks.append({"check": "finding_evidence", "id": f["id"], "passed": True})

    finding_ids = {f["id"] for f in kept_findings}
    finding_review_ids = set()
    for f in kept_findings:
        finding_review_ids.update(f["evidence_review_ids"])

    for r in requirements:
        fids = [i for i in r.get("finding_ids", []) if i in finding_ids]
        rids = [i for i in r.get("review_ids", []) if i in review_ids]
        if not fids and not rids:
            r["status"] = "assumption"
            r["note"] = "无有效发现/评论支持，已标记为假设"
            assumption_requirements.append(r["code"])
            checks.append({"check": "requirement_support", "id": r["code"], "passed": False, "detail": "无支持证据，标记为 assumption"})
        else:
            r["finding_ids"] = fids
            r["review_ids"] = rids
            kept_requirements.append(r)
            checks.append({"check": "requirement_support", "id": r["code"], "passed": True})

    kept_req_codes = {r["code"] for r in kept_requirements}

    for tc in test_cases:
        req_ids = [i for i in tc.get("requirement_ids", []) if i in kept_req_codes]
        if not req_ids:
            removed_tests.append(tc["code"])
            checks.append({"check": "testcase_link", "id": tc["code"], "passed": False, "detail": "链接的需求被移除，测试用例已移除"})
        else:
            tc["requirement_ids"] = req_ids
            kept_tests.append(tc)
            checks.append({"check": "testcase_link", "id": tc["code"], "passed": True})

    for r in kept_requirements:
        linked = set()
        for f in kept_findings:
            if f["id"] in r.get("finding_ids", []):
                linked.update(f["evidence_review_ids"])
        missing = [i for i in r.get("review_ids", []) if i not in linked and i not in r.get("finding_ids", [])]
        checks.append({
            "check": "requirement_review_chain",
            "id": r["code"],
            "passed": not missing,
            "detail": "链路完整" if not missing else "评论未出现在来源发现中",
            "missing": missing[:10],
        })

    passed = all(c["passed"] for c in checks)
    return {
        "ok": passed,
        "checks": checks,
        "findings": kept_findings,
        "requirements": kept_requirements,
        "test_cases": kept_tests,
        "removed_findings": removed_findings,
        "removed_test_cases": removed_tests,
        "assumption_requirements": assumption_requirements,
        "summary": {
            "total_checks": len(checks),
            "passed_checks": sum(1 for c in checks if c["passed"]),
            "failed_checks": sum(1 for c in checks if not c["passed"]),
        },
    }
