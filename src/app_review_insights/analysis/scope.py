"""S0 范围解析：规则种子 + LLM 结构化抽取，失败时安全回退默认全量。"""

from __future__ import annotations

from typing import Optional

DEFAULT_SCOPE = {
    "focus_areas": [],
    "star_filter": {"min": None, "max": None},
    "version_filter": None,
    "note": "默认全量分析",
}

KEYWORD_FOCUS = {
    "subscription_conversion": ["订阅", "续费", "付费", "免费试用", "subscription", "premium", "paywall"],
    "usability": ["难用", "复杂", "易用", "操作", "usability", "confusing", "difficult"],
    "performance": ["卡", "闪退", "崩溃", "慢", "crash", "lag", "slow", "bug"],
    "pricing": ["价格", "贵", "便宜", "price", "expensive", "cost"],
}


def _seed_focus(goal_text: str) -> list[str]:
    text = goal_text.lower()
    return [key for key, words in KEYWORD_FOCUS.items() if any(w in text for w in words)]


def parse_scope(goal_text: str, llm: Optional[object] = None) -> dict:
    scope = dict(DEFAULT_SCOPE)
    seeded = _seed_focus(goal_text)
    if seeded:
        scope["focus_areas"] = seeded
        scope["note"] = "规则种子识别 + 待模型细化"
    if llm is None:
        return scope
    try:
        from ..prompts import scope_messages

        result = llm.chat_json(scope_messages(goal_text))
        data = result.get("scope") or result
        if isinstance(data.get("focus_areas"), list):
            scope["focus_areas"] = sorted(set(data["focus_areas"]))
        star = data.get("star_filter")
        if isinstance(star, dict):
            scope["star_filter"] = {
                "min": star.get("min") if isinstance(star.get("min"), int) else None,
                "max": star.get("max") if isinstance(star.get("max"), int) else None,
            }
        scope["version_filter"] = data.get("version_filter") or None
        scope["note"] = f"模型解析（{data.get('note') or '见 focus_areas'}）"
    except Exception as exc:  # noqa: BLE001
        scope["note"] = f"模型解析失败，使用规则种子/默认范围：{exc}"
    return scope
