"""S4 证据评估与发现生成：统计发现（规则）+ 模型发现（LLM）+ 冲突/置信度标注。"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Optional


def _topic_reviews(reviews: list[dict], memberships: list[dict]) -> dict[int, list[dict]]:
    groups: dict[int, list[dict]] = defaultdict(list)
    by_key = {r["review_key"]: r for r in reviews}
    for m in memberships:
        review = by_key.get(m["review_key"])
        if review is not None:
            groups[m["topic_id"]].append(review)
    return groups


def _sample_reviews(reviews: list[dict], limit: int = 8) -> list[dict]:
    ordered = sorted(reviews, key=lambda r: (-r.get("helpful_votes", 0), r["review_key"]))
    return ordered[:limit]


def _topic_stats(reviews: list[dict], label: str, topic_id: int) -> dict:
    n = len(reviews)
    ratings = [r.get("rating", 0) for r in reviews if r.get("rating")]
    avg = round(sum(ratings) / len(ratings), 2) if ratings else None
    return {
        "id": f"F-stat-{topic_id}",
        "topic_id": topic_id,
        "statement": f"主题「{label}」共出现 {n} 条相关评论，平均评分 {avg if avg is not None else '未知'}。",
        "evidence_review_ids": [r["review_key"] for r in reviews],
        "sample_count": n,
        "confidence": 1.0 if n >= 10 else round(n / 10, 2),
        "uncertainty": "样本量有限，结论强度受限" if n < 10 else "无",
        "conflicts": [],
        "provenance": "stat",
        "status": "kept",
        "rationale": "确定性统计：样本数、评分分布。",
    }


def _detect_conflicts(reviews: list[dict]) -> list[str]:
    low = [r for r in reviews if r.get("rating") and r["rating"] <= 2]
    high = [r for r in reviews if r.get("rating") and r["rating"] >= 4]
    if low and high:
        return [f"{len(low)} 条低分与 {len(high)} 条高分反馈并存，观点存在分歧"]
    return []


def build_findings(
    reviews: list[dict],
    topics: dict,
    llm: Optional[object] = None,
    *,
    max_model_findings_per_topic: int = 3,
) -> list[dict]:
    """生成发现列表：stat 兜底 + model 增强；模型输出执行引用白名单校验。"""
    findings: list[dict] = []
    groups = _topic_reviews(reviews, topics["memberships"])
    label_by_id = {t["topic_id"]: t.get("label", f"主题{t['topic_id']}") for t in topics["topics"]}

    for topic_id in sorted(groups):
        members = groups[topic_id]
        label = label_by_id.get(topic_id, f"主题{topic_id}")
        stat_finding = _topic_stats(members, label, topic_id)
        stat_finding["conflicts"] = _detect_conflicts(members)
        findings.append(stat_finding)

        if llm is None or len(members) < 2:
            continue
        samples = _sample_reviews(members, limit=8)
        allowed = {r["review_key"] for r in members}
        try:
            from ..prompts import findings_messages

            result = llm.chat_json(findings_messages({
                "label": label,
                "samples": [
                    {
                        "review_id": r["review_key"],
                        "rating": r.get("rating", 0),
                        "version": r.get("version", ""),
                        "text": (r.get("title", "") + " " + r.get("body", "")).strip()[:300],
                    }
                    for r in samples
                ],
            }))
            items = result.get("findings") or []
            model_count = 0
            for item in items[:max_model_findings_per_topic]:
                if not isinstance(item, dict):
                    continue
                evidence = [str(i) for i in (item.get("evidence_review_ids") or [])]
                valid = [i for i in evidence if i in allowed]
                if not valid:
                    continue  # 引用白名单：非法引用直接丢弃
                model_count += 1
                confidence = float(item.get("confidence", 0.5))
                findings.append({
                    "id": f"F-model-{topic_id}-{model_count}",
                    "topic_id": topic_id,
                    "statement": str(item.get("statement") or "").strip(),
                    "evidence_review_ids": valid,
                    "sample_count": len(valid),
                    "confidence": max(0.0, min(1.0, confidence)),
                    "uncertainty": str(item.get("uncertainty") or "").strip(),
                    "conflicts": [str(c) for c in (item.get("conflicts") or [])],
                    "provenance": "model",
                    "status": "kept",
                    "rationale": "模型基于引用白名单内的评论生成，输出经 JSON Schema 校验。",
                })
        except Exception as exc:  # noqa: BLE001
            findings.append({
                "id": f"F-model-{topic_id}-0",
                "topic_id": topic_id,
                "statement": f"主题「{label}」的模型级深入分析未完成（{exc}），保留统计发现。",
                "evidence_review_ids": [r["review_key"] for r in samples],
                "sample_count": len(samples),
                "confidence": 0.0,
                "uncertainty": "模型调用失败，结论不可用",
                "conflicts": _detect_conflicts(members),
                "provenance": "model",
                "status": "removed",
                "rationale": "模型不可用，未生成可支持结论。",
            })
    return findings
