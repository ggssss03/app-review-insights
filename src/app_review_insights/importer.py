"""导入外部 JSON/CSV 评论数据（README R10 要求）。"""

from __future__ import annotations

import csv
import json
import pathlib
from typing import Any, Iterable, Optional

from .models import ReviewRaw, utcnow_iso
from .storage import write_json


def _label(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("label", "")).strip()
    if value is None:
        return ""
    return str(value).strip()


def _pick(mapping: dict, *paths: str) -> Any:
    """按多个候选键取值，支持 a.b.c 路径与嵌套 dict。"""
    for path in paths:
        node: Any = mapping
        found = True
        for part in path.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                found = False
                break
        if found and node is not None:
            return node
    return None


def _as_int(value: Any) -> int:
    if isinstance(value, dict):
        value = value.get("label")
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def from_mapping(mapping: dict, *, source: str, app_id: str, country: str = "us",
                 page_url: str = "", sort_by: str = "") -> ReviewRaw:
    """把一行（dict 或 CSV 行）归一化为 ReviewRaw，兼容常见字段名。"""
    rating = _as_int(_pick(mapping, "rating", "stars", "im:rating", "score"))
    return ReviewRaw.create(
        source=source,
        app_id=app_id,
        review_id=_label(_pick(mapping, "id", "review_id", "reviewId", "review.id")),
        author=_label(_pick(mapping, "author.name.label", "author.name", "author",
                            "author_name", "authorName", "name")),
        rating=rating,
        title=_label(_pick(mapping, "title", "title.label")),
        body=_label(_pick(mapping, "content", "body", "text", "review", "content.label")),
        version=_label(_pick(mapping, "version", "app_version", "appVersion", "im:version")),
        country=_label(_pick(mapping, "country", "storefront")) or country,
        updated=_label(_pick(mapping, "updated", "date", "created_at", "createdAt", "updated.label")),
        helpful_votes=_as_int(_pick(mapping, "votes", "helpful_votes", "voteSum", "im:voteSum", "helpfulVotes")),
        page_url=page_url,
        sort_by=sort_by,
        raw=dict(mapping),
    )


def import_json_file(path: pathlib.Path, *, app_id: str, country: str = "us") -> list[ReviewRaw]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        # 支持 RSS feed 结构与 envelope 结构
        if "data" in payload and isinstance(payload["data"], list):
            payload = payload["data"]
        elif "feed" in payload and "entry" in payload["feed"]:
            payload = payload["feed"]["entry"]
        elif "entry" in payload:
            payload = payload["entry"]
        else:
            raise ValueError("JSON 结构无法识别：应为评论数组、RSS feed 或带 data 数组的信封")
    if not isinstance(payload, list):
        raise ValueError("JSON 顶层应为评论数组")
    return [from_mapping(item, source="import", app_id=app_id, country=country) for item in payload]


def import_csv_file(path: pathlib.Path, *, app_id: str, country: str = "us") -> list[ReviewRaw]:
    reviews = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            reviews.append(from_mapping(dict(row), source="import", app_id=app_id, country=country))
    return reviews


def import_reviews(path: pathlib.Path, *, app_id: str, country: str = "us") -> list[ReviewRaw]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return import_json_file(path, app_id=app_id, country=country)
    if suffix == ".csv":
        return import_csv_file(path, app_id=app_id, country=country)
    raise ValueError(f"不支持的文件类型：{suffix}（仅支持 .json / .csv）")


def save_imported(reviews: Iterable[ReviewRaw], out_path: pathlib.Path) -> dict:
    rows = [r.to_dict() for r in reviews]
    write_json(out_path, {
        "source": "import",
        "count": len(rows),
        "imported_at": utcnow_iso(),
        "reviews": rows,
    })
    return {"count": len(rows), "path": str(out_path)}
