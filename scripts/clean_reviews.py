"""清洗 data/raw/<app_id>/ 下的评论，输出 data/processed/<app_id>/。

用法示例：
    python scripts/clean_reviews.py 839285684
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from app_review_insights.cleaner import clean_reviews  # noqa: E402
from app_review_insights.models import ReviewRaw  # noqa: E402
from app_review_insights.storage import ensure_dir, write_csv, write_json  # noqa: E402


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


def main() -> int:
    parser = argparse.ArgumentParser(description="清洗评论并输出结构化结果")
    parser.add_argument("app_id", help="应用 id（对应 data/raw/<app_id>）")
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--out-dir", default="data/processed")
    args = parser.parse_args()

    raw_dir = pathlib.Path(args.raw_dir) / args.app_id
    out_dir = pathlib.Path(args.out_dir) / args.app_id
    ensure_dir(out_dir)

    raw_reviews = load_raw_reviews(raw_dir, args.app_id)
    if not raw_reviews:
        print("没有可清洗的原始评论（请先用 fetch_reviews 或 import_reviews 准备数据）。", file=sys.stderr)
        return 1
    result = clean_reviews(raw_reviews)
    reviews = result["reviews"]
    stats = result["stats"]
    write_json(out_dir / "reviews_clean.json", {"app_id": args.app_id, "stats": stats, "reviews": reviews})
    write_json(out_dir / "stats.json", stats)
    fieldnames = [
        "source", "app_id", "review_id", "dedup_key", "author", "rating", "title", "body",
        "version", "country", "updated", "helpful_votes", "lang", "lang_method",
        "is_junk", "junk_reason", "pii_scrubbed", "sort_by", "fetched_at",
    ]
    write_csv(out_dir / "reviews_clean.csv", reviews, fieldnames)
    print(f"输入 {stats['input_count']} -> 去重后 {stats['unique_count']}，"
          f"其中垃圾 {stats['junk_count']} 条")
    print(f"输出 -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
