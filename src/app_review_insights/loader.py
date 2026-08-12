"""从 data/raw/<app_id>/ 加载原始评论（RSS 页缓存 + 导入数据集）。"""

from __future__ import annotations

import json
import pathlib

from .collector import parse_amp_page_shelf_reviews, parse_itml_payload
from .models import ReviewRaw, utcnow_iso


def load_raw_reviews(raw_dir: pathlib.Path, app_id: str) -> list[ReviewRaw]:
    reviews: list[ReviewRaw] = []
    for file in sorted(raw_dir.glob("*.json")):
        if file.name in ("app.json", "collection_notes.json"):
            continue
        if file.name == "imported-reviews.json":
            payload = json.loads(file.read_text(encoding="utf-8"))
            for row in payload.get("reviews", []):
                reviews.append(ReviewRaw.create(
                    source="import",
                    app_id=app_id,
                    review_id=row.get("review_id", ""),
                    author=row.get("author", ""),
                    rating=row.get("rating", 0),
                    title=row.get("title", ""),
                    body=row.get("body", ""),
                    version=row.get("version", ""),
                    updated=row.get("updated", ""),
                    helpful_votes=row.get("helpful_votes", 0),
                    raw=row,
                ))
            continue
        payload = json.loads(file.read_text(encoding="utf-8"))
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("userReviewList"), list):
            reviews.extend(parse_itml_payload(
                data, source="itml", app_id=app_id, country="us",
                page_url=payload.get("url", ""), sort_by="mostRecent",
                fetched_at=payload.get("fetched_at", utcnow_iso()),
            ))
            continue
        if isinstance(data, dict) and isinstance(data.get("shelfMapping"), dict):
            reviews.extend(parse_amp_page_shelf_reviews(
                {"data": [{"data": data}]}, source="amp-page", app_id=app_id,
                country="cn", page_url=payload.get("url", ""),
            ))
            continue
        feed = payload.get("data", {}).get("feed", payload.get("feed", {}))
        entry = feed.get("entry", []) if isinstance(feed, dict) else []
        if isinstance(entry, dict):
            entry = [entry]
        for item in entry:
            reviews.append(ReviewRaw.create(
                source="rss",
                app_id=app_id,
                review_id=str(item.get("id", {}).get("label", "")),
                author=str(item.get("author", {}).get("name", {}).get("label", "")),
                rating=int(float(str(item.get("im:rating", {}).get("label", 0))) or 0),
                title=str(item.get("title", {}).get("label", "")),
                body=str(item.get("content", {}).get("label", "")),
                version=str(item.get("im:version", {}).get("label", "")),
                updated=str(item.get("updated", {}).get("label", "")),
                raw=item,
            ))
    return reviews
