"""采集 App Store 应用元数据与评论（美国区官方接口），并缓存到 data/raw/。

用法示例：
    python scripts/fetch_reviews.py 839285684
    python scripts/fetch_reviews.py https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from app_review_insights.collector import (  # noqa: E402
    SORT_ORDERS,
    extract_app_id,
    fetch_reviews,
    lookup_app,
)
from app_review_insights.storage import envelope, write_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="采集 App Store 元数据与评论（US 区）")
    parser.add_argument("app", help="App Store 链接或数字 app id")
    parser.add_argument("--country", default="us")
    parser.add_argument("--sorts", default=",".join(SORT_ORDERS), help="逗号分隔的排序方式")
    parser.add_argument("--pages", type=int, default=10, help="每个排序最多采集页数（每页 50 条）")
    parser.add_argument("--delay", type=float, default=1.0, help="请求间隔秒数（礼貌限速）")
    parser.add_argument("--cache-dir", default="data/raw", help="原始缓存目录")
    args = parser.parse_args()

    app_id = extract_app_id(args.app)
    cache_dir = pathlib.Path(args.cache_dir) / app_id
    sort_orders = tuple(s.strip() for s in args.sorts.split(",") if s.strip())

    print(f"[1/2] 获取应用元数据: {app_id}")
    try:
        info = lookup_app(app_id, country=args.country)
        write_json(cache_dir / "app.json", envelope(app_id, info.url, info.to_dict(), info.fetched_at))
        print(f"      {info.track_name} | {info.genre} | 评分 {info.avg_rating:.2f} ({info.rating_count})")
    except Exception as exc:  # noqa: BLE001
        print(f"      [警告] 元数据获取失败：{exc}", file=sys.stderr)

    print(f"[2/2] 采集评论 (sorts={sort_orders}, pages<= {args.pages})")
    stats = fetch_reviews(
        app_id,
        country=args.country,
        sort_orders=sort_orders,
        max_pages=args.pages,
        delay=args.delay,
        cache_dir=cache_dir,
    )
    print(f"      新抓页 {stats['pages_fetched']}，跳过缓存 {stats['pages_skipped']}，"
          f"累计评论 {stats['reviews_total']}")
    if stats["empty_pages"]:
        print(f"      [注意] {len(stats['empty_pages'])} 页返回空 feed（地区/网络限制时正常）"
              f"，请使用 GitHub Actions 采集或导入 JSON/CSV。", file=sys.stderr)
    for err in stats["errors"]:
        print(f"      [错误] {err['url']}: {err['error']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
