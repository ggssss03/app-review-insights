"""流水线编排器：S0-S8 阶段状态机，带进度事件、每阶段缓存与断点续跑。"""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any, Callable, Optional

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


def _goal_fingerprint(goal_text: str) -> str:
    """目标文本指纹：scope 缓存只在目标一致时可复用，避免串用上一次分析的范围。"""
    normalized = " ".join(goal_text.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]


# 依赖分析目标的阶段：目标变化时必须重跑，否则会串用上一次分析的结果
_GOAL_DEPENDENT_STAGES = {"scope", "topics", "findings", "requirements", "testcases", "traceability"}


def _read_cached(path: pathlib.Path, *, goal_fp: Optional[str] = None, sidecar: Optional[pathlib.Path] = None) -> Any:
    """读取阶段缓存；目标相关阶段通过侧车文件校验 goal 指纹，不匹配视为未缓存。"""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if goal_fp is not None:
        try:
            meta = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar else None
        except Exception:
            meta = None
        if not isinstance(meta, dict) or meta.get("_goal_fp") != goal_fp:
            return None
    return payload


def _apply_scope(reviews: list[dict], scope: dict) -> list[dict]:
    """按 S0 解析出的评分/版本筛选收紧进入下游分析的评论集合。"""
    star = scope.get("star_filter") or {}
    vmin, vmax = star.get("min"), star.get("max")
    version = scope.get("version_filter")
    out = reviews
    if vmin is not None or vmax is not None:
        out = [
            r for r in out
            if (vmin is None or (r.get("rating") or 0) >= vmin)
            and (vmax is None or (r.get("rating") or 0) <= vmax)
        ]
    if version:
        out = [r for r in out if str(r.get("version") or "") == str(version)]
    return out


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

    def stage(name: str, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        cache = analysis_dir / f"{name}.json"
        goal_fp = _goal_fingerprint(goal_text) if name in _GOAL_DEPENDENT_STAGES else None
        sidecar = analysis_dir / f"{name}.goal.json" if goal_fp is not None else None
        result = None if force else _read_cached(cache, goal_fp=goal_fp, sidecar=sidecar)
        if result is not None:
            events.append({"stage": name, "status": "cached", "detail": "使用缓存结果"})
            return result
        result = fn(*args, **kwargs)
        write_json(cache, result)
        if sidecar is not None:
            write_json(sidecar, {"_goal_fp": goal_fp})
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

    scoped_reviews = _apply_scope(reviews, scope)
    if not scoped_reviews:
        events.append({"stage": "scope", "status": "ok", "detail": "范围筛选后无评论，已回退全量分析"})
        scoped_reviews = reviews

    topics = stage(
        "topics", discover_topics, scoped_reviews,
        embed_backend=embed_backend, llm=llm, goal_text=goal_text,
    )
    focus_areas = scope.get("focus_areas") or None
    findings = stage("findings", build_findings, scoped_reviews, topics, llm, focus_areas=focus_areas)
    requirements, req_note = stage("requirements", generate_requirements, findings, llm, focus_areas=focus_areas)
    test_cases, tc_note = stage("testcases", generate_test_cases, requirements, llm)
    trace = stage("traceability", validate_traceability, reviews, findings, requirements, test_cases)

    summary_scope = dict(scope)
    summary = {
        "app_id": app_id,
        "goal_text": goal_text,
        "scope": summary_scope,
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
