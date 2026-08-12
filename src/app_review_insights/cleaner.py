"""清洗/去重/结构化（README R5：此阶段全部用确定性规则，结果稳定可审计）。"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Iterable, Optional

from .models import ReviewRaw

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\w)\+?[\d][\d\s().-]{7,}\d(?!\w)")


def scrub_pii(text: str) -> str:
    """脱敏：掩码邮箱与电话，保留 URL。"""
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = PHONE_RE.sub("[PHONE]", text)
    return text


def detect_lang(text: str) -> str:
    """轻量脚本启发式语言识别（标注为 heuristic，后续可换模型）。"""
    if not text.strip():
        return "unknown"
    counts = Counter()
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            counts["han"] += 1
        elif "\u3040" <= ch <= "\u30ff":
            counts["kana"] += 1
        elif "\uac00" <= ch <= "\ud7af":
            counts["hangul"] += 1
        elif "\u0600" <= ch <= "\u06ff":
            counts["arabic"] += 1
        elif "\u0400" <= ch <= "\u04ff":
            counts["cyrillic"] += 1
        elif ("a" <= ch.lower() <= "z") or ("\u00c0" <= ch <= "\u024f"):
            counts["latin"] += 1
    total = sum(counts.values())
    if total == 0:
        return "symbols"
    top, top_count = counts.most_common(1)[0]
    if top == "han":
        return "ja" if counts.get("kana", 0) >= total * 0.1 else "zh"
    if top == "latin":
        return "en"
    return {"kana": "ja", "hangul": "ko", "arabic": "ar", "cyrillic": "ru"}.get(top, "other")


def is_junk(review: ReviewRaw) -> tuple[bool, str]:
    text = f"{review.title} {review.body}".strip()
    if len(text) < 2:
        return True, "too_short"
    letters = sum(1 for ch in text if ch.isalnum())
    if letters == 0:
        return True, "no_text"
    if letters / max(len(text), 1) < 0.15 and len(text) > 4:
        return True, "mostly_symbols"
    return False, ""


def dedup_key(review: ReviewRaw) -> str:
    if review.review_id:
        return f"id:{review.review_id}"
    payload = "|".join([
        review.author.lower(),
        review.updated,
        review.title.lower(),
        review.body.lower()[:200],
    ])
    return "hash:" + hashlib.sha1(payload.encode("utf-8")).hexdigest()


def clean_reviews(raw_reviews: Iterable[ReviewRaw]) -> dict:
    """去重 + 清洗 + 统计。返回 {reviews, stats}。"""
    seen_ids: set[str] = set()
    seen_content: dict[str, tuple[str, str]] = {}  # content_fp -> (author, updated)
    removed_dupes = 0
    cleaned = []
    rating_dist: Counter = Counter()
    lang_dist: Counter = Counter()
    junk_count = 0

    for raw in raw_reviews:
        if raw.review_id and raw.review_id in seen_ids:
            removed_dupes += 1
            continue
        content_fp = hashlib.sha1(
            f"{raw.title.lower()}|{raw.body.lower()[:200]}".encode("utf-8")
        ).hexdigest()
        if content_fp in seen_content:
            prev_author, prev_updated = seen_content[content_fp]
            same_author = prev_author == raw.author.lower()
            same_time = bool(prev_updated) and prev_updated == raw.updated
            if same_author or same_time:
                removed_dupes += 1
                continue
        seen_content[content_fp] = (raw.author.lower(), raw.updated)
        if raw.review_id:
            seen_ids.add(raw.review_id)
        junk, junk_reason = is_junk(raw)
        rating = raw.rating if 1 <= raw.rating <= 5 else 0
        rating_dist[rating] += 1
        body = scrub_pii(raw.body)
        title = scrub_pii(raw.title)
        lang = detect_lang(f"{title} {body}")
        lang_dist[lang] += 1
        if junk:
            junk_count += 1
        cleaned.append({
            "source": raw.source,
            "app_id": raw.app_id,
            "review_id": raw.review_id,
            "dedup_key": dedup_key(raw),
            "author": raw.author,
            "rating": rating,
            "title": title,
            "body": body,
            "version": raw.version,
            "country": raw.country,
            "updated": raw.updated,
            "helpful_votes": raw.helpful_votes,
            "lang": lang,
            "lang_method": "script-heuristic",
            "is_junk": junk,
            "junk_reason": junk_reason if junk else "",
            "pii_scrubbed": True,
            "sort_by": raw.sort_by,
            "fetched_at": raw.fetched_at,
        })

    stats = {
        "input_count": len(cleaned) + removed_dupes,
        "unique_count": len(cleaned),
        "removed_duplicates": removed_dupes,
        "junk_count": junk_count,
        "rating_distribution": {str(k): v for k, v in sorted(rating_dist.items())},
        "language_distribution": dict(lang_dist),
        "rules_note": "清洗/去重/语言识别使用确定性规则（详见 PLAN.md 第 7 节）。",
    }
    return {"reviews": cleaned, "stats": stats}
