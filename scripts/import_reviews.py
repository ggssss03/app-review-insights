"""导入 JSON/CSV 评论数据到 data/raw/<app_id>/imported-reviews.json。

用法示例：
    python scripts/import_reviews.py reviews.csv --app-id 839285684
    python scripts/import_reviews.py reviews.json --app-id 839285684
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from app_review_insights.importer import import_reviews, save_imported  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="导入 JSON/CSV 评论数据")
    parser.add_argument("file", help="评论文件路径（.json 或 .csv）")
    parser.add_argument("--app-id", required=True, help="目标应用 id")
    parser.add_argument("--country", default="us")
    parser.add_argument("--out", default=None, help="输出文件路径（默认 data/raw/<app_id>/imported-reviews.json）")
    args = parser.parse_args()

    path = pathlib.Path(args.file)
    if not path.exists():
        print(f"文件不存在：{path}", file=sys.stderr)
        return 1
    reviews = import_reviews(path, app_id=args.app_id, country=args.country)
    out = pathlib.Path(args.out) if args.out else pathlib.Path("data/raw") / args.app_id / "imported-reviews.json"
    result = save_imported(reviews, out)
    print(f"已导入 {result['count']} 条评论 -> {result['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
