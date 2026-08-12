"""流水线编排器：S0-S8 阶段状态机，带进度事件、每阶段缓存与断点续跑。"""

from __future__ import annotations

import json
import pathlib
from typing import Optional

from ..cleaner import clean_reviews
from ..loader import load_raw_reviews
from ..storage import ensure_dir, write_json
from .findings import build_findings
from .planning import generate_requirements, generate_test_cases
from .scope import parse_scope
from .topics import discover_topics
from .traceability import validate_traceability


def _prepare(reviews_clean: list[dict]) -> list[dict]:
    prepared = []
    for i, r in enumerate(reviews_clean):
        item = dict(r)
        item["review_key"] = r.get("review_id") or f"row-{i}"
        item["text"] = f"{r.get('title', '')} {r.get('body', '')}".strip()
        prepared.append(item)
    return prepared


def run_pipeline(
    *,
    app_id: str,
    raw_dir: pathlib.Path,
    out_dir: pathlib.Path,
    goal_text: str = "",
    llm: Optional[object] = None,
    embed_backend: str = "auto",
    force: bool = False,
    progress: Optional[list] = None,
) -> dict:
    ensure_dir(out_dir / "analysis")
    analysis_dir = out_dir / "analysis"
    events: list[dict] = progress if progress is not None else []

    def stage(name: str, fn, *args, **kwargs):
        cache = analysis_dir / f"{name}.json"
        if cache.exists() and not force:
            with cache.open(encoding="utf-8") as f:
                result = json.load(f)
            events.append({"stage": name, "status": "cached", "detail": "使用缓存结果"})
            return result
        result = fn(*args, **kwargs)
        write_json(cache, result)
        events.append({"stage": name, "status": "ok", "detail": "完成"})
        return result

    scope = stage("scope", parse_scope, goal_text, llm)

    raw_reviews = load_raw_reviews(raw_dir, app_id)
    if not raw_reviews:
        events.append({"stage": "load", "status": "error", "detail": "没有原始评论，请先采集或导入"})
        raise RuntimeError("没有原始评论数据")
    events.append({"stage": "load", "status": "ok", "detail": f"{len(raw_reviews)} 条原始评论"})

    clean = stage("clean", clean_reviews, raw_reviews)
    reviews = _prepare(clean["reviews"])
    events.append({
        "stage": "clean",
        "status": "ok",
        "detail": f"{len(reviews)} 条（去重 {clean['stats']['removed_duplicates']}，垃圾 {clean['stats']['junk_count']}）",
    })

    topics = stage("topics", discover_topics, reviews, embed_backend=embed_backend, llm=llm)
    findings = stage("findings", build_findings, reviews, topics, llm)
    requirements, req_note = stage("requirements", generate_requirements, findings, llm)
    test_cases, tc_note = stage("testcases", generate_test_cases, requirements, llm)
    trace = stage("traceability", validate_traceability, reviews, findings, requirements, test_cases)

    summary = {
        "app_id": app_id,
        "goal_text": goal_text,
        "scope": scope,
        "clean_stats": clean["stats"],
        "counts": {
            "reviews": len(reviews),
            "topics": len(topics["topics"]),
            "findings": len(trace["findings"]),
            "requirements": len(trace["requirements"]),
            "test_cases": len(trace["test_cases"]),
        },
        "model_driven": llm is not None,
        "notes": [
            req_note,
            tc_note,
            f"主题发现使用 {topics['embed_backend']} 嵌入；模型驱动主题命名：{topics['model_driven']}。",
            "数据来源与限制见 data/README.md；空数据/网络限制如实标注，不编造。",
        ],
        "traceability": trace["summary"],
    }
    write_json(analysis_dir / "summary.json", summary)
    write_json(analysis_dir / "progress.json", events)
    events.append({"stage": "summary", "status": "ok", "detail": "汇总完成"})
    return {
        "summary": summary,
        "events": events,
        "artifacts": {
            "scope": analysis_dir / "scope.json",
            "clean": analysis_dir / "clean.json",
            "topics": analysis_dir / "topics.json",
            "findings": analysis_dir / "findings.json",
            "requirements": analysis_dir / "requirements.json",
            "test_cases": analysis_dir / "testcases.json",
            "traceability": analysis_dir / "traceability.json",
        },
    }
