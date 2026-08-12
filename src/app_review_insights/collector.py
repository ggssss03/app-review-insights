"""App Store 数据采集（官方公共接口）。

- 应用元数据：iTunes Lookup API
- 评论数据：iTunes Customer Reviews RSS（美国区 storefront）
不爬页面可见内容；请求间隔 >= delay 秒；原始响应按页缓存，可断点续采。
"""

from __future__ import annotations

import json
import pathlib
import re
import time
import urllib.parse
import urllib.request
from typing import Optional

from .models import AppInfo, ReviewRaw, utcnow_iso
from .storage import envelope, ensure_dir, write_json

ITUNES_LOOKUP_URL = "https://itunes.apple.com/lookup"
RSS_BASE_URL = "https://itunes.apple.com/us/rss/customerreviews"
SORT_ORDERS = ("mostRecent", "mostHelpful")
MAX_PAGES = 10
USER_AGENT = "app-review-insights/0.1 (local demo collector)"

REVIEW_ID_PATTERN = re.compile(r"(?:[?&]id=|/id)(\d+)")


def http_get_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_app_id(url_or_id: str) -> str:
    """从 App Store URL 或裸 id 中提取 app id。"""
    text = url_or_id.strip()
    if text.isdigit():
        return text
    m = REVIEW_ID_PATTERN.search(text)
    if m:
        return m.group(1)
    raise ValueError(f"无法从输入中解析 App Store 应用 id: {url_or_id!r}")


def lookup_app(app_id: str, country: str = "us", timeout: int = 30) -> AppInfo:
    url = f"{ITUNES_LOOKUP_URL}?id={urllib.parse.quote(app_id)}&country={urllib.parse.quote(country)}"
    payload = http_get_json(url, timeout=timeout)
    results = payload.get("results") or []
    if not results:
        raise LookupError(f"Lookup 未返回结果：{url}")
    return AppInfo.from_lookup(app_id, results[0], storefront=country)


def build_rss_url(app_id: str, sort_by: str, page: int, country: str = "us") -> str:
    if country != "us":
        return (f"https://itunes.apple.com/{urllib.parse.quote(country)}/rss/customerreviews"
                f"/id={urllib.parse.quote(app_id)}/page={page}/sortBy={urllib.parse.quote(sort_by)}/json")
    return f"{RSS_BASE_URL}/id={app_id}/page={page}/sortBy={sort_by}/json"


def _label(entry: dict, *keys: str) -> str:
    for key in keys:
        if key in entry:
            value = entry[key]
            if isinstance(value, dict):
                return str(value.get("label", "")).strip()
            if value is not None:
                return str(value).strip()
    return ""


def parse_review_entry(entry: dict, *, source: str, app_id: str, country: str,
                       page_url: str, sort_by: str, fetched_at: str) -> Optional[ReviewRaw]:
    """解析 RSS 的一条 entry（JSON 版字段名形如 im:rating / content / title）。"""
    if not isinstance(entry, dict):
        return None
    rating_raw = _label(entry, "im:rating", "rating", "stars")
    try:
        rating = int(float(rating_raw))
    except (TypeError, ValueError):
        rating = 0
    author_raw = entry.get("author") or {}
    if isinstance(author_raw, dict):
        author = _label(author_raw.get("name", {}), "label") if isinstance(author_raw.get("name"), dict) else str(author_raw.get("name", "")).strip()
    else:
        author = str(author_raw).strip()
    votes_raw = _label(entry, "im:voteSum", "voteSum", "helpful_votes")
    try:
        votes = int(float(votes_raw))
    except (TypeError, ValueError):
        votes = 0
    return ReviewRaw.create(
        source=source,
        app_id=app_id,
        review_id=_label(entry, "id"),
        author=author,
        rating=rating,
        title=_label(entry, "title"),
        body=_label(entry, "content", "body", "text"),
        version=_label(entry, "im:version", "version", "app_version"),
        country=country,
        updated=_label(entry, "updated", "date"),
        helpful_votes=votes,
        page_url=page_url,
        sort_by=sort_by,
        raw=entry,
    )


def parse_review_feed(payload: dict, *, source: str, app_id: str, country: str,
                      page_url: str, sort_by: str, fetched_at: str) -> list[ReviewRaw]:
    """解析 RSS JSON 响应；feed.entry 可能是列表或单对象，也可能为空。"""
    feed = payload.get("feed") or {}
    entry = feed.get("entry") or []
    if isinstance(entry, dict):
        entry = [entry]
    reviews = []
    for item in entry:
        review = parse_review_entry(
            item, source=source, app_id=app_id, country=country,
            page_url=page_url, sort_by=sort_by, fetched_at=fetched_at,
        )
        if review is not None:
            reviews.append(review)
    return reviews


def fetch_reviews(
    app_id: str,
    *,
    country: str = "us",
    sort_orders: tuple[str, ...] = SORT_ORDERS,
    max_pages: int = MAX_PAGES,
    delay: float = 1.0,
    cache_dir: pathlib.Path,
    timeout: int = 30,
) -> dict:
    """采集评论并缓存；已存在的缓存页跳过（断点续采）。"""
    ensure_dir(cache_dir)
    fetched_at = utcnow_iso()
    stats = {
        "app_id": app_id,
        "country": country,
        "fetched_at": fetched_at,
        "pages_fetched": 0,
        "pages_skipped": 0,
        "reviews_total": 0,
        "reviews_by_sort": {},
        "empty_pages": [],
        "errors": [],
        "notes": [
            "数据来源：Apple iTunes Customer Reviews RSS（官方公共接口）。",
            "注意：美国区评论 RSS 在部分地区网络下可能返回空 feed（例如中国大陆直连）。"
            "此情况下请使用 GitHub Actions 采集工作流或导入 JSON/CSV 数据集。",
        ],
    }
    for sort_by in sort_orders:
        reviews_for_sort = []
        for page in range(1, max_pages + 1):
            url = build_rss_url(app_id, sort_by, page, country=country)
            cache_file = cache_dir / f"reviews-{sort_by}-p{page}.json"
            if cache_file.exists():
                payload = json.loads(cache_file.read_text(encoding="utf-8"))
                stats["pages_skipped"] += 1
            else:
                try:
                    payload = http_get_json(url, timeout=timeout)
                    write_json(cache_file, envelope(app_id, url, payload, fetched_at))
                    stats["pages_fetched"] += 1
                    time.sleep(delay)
                except Exception as exc:  # noqa: BLE001 - 记录网络错误，不中断整个采集
                    stats["errors"].append({"url": url, "error": str(exc)})
                    break
            reviews = parse_review_feed(
                payload, source="rss", app_id=app_id, country=country,
                page_url=url, sort_by=sort_by, fetched_at=fetched_at,
            )
            reviews_for_sort.extend(reviews)
            if not reviews:
                stats["empty_pages"].append({"sort_by": sort_by, "page": page, "url": url})
                # RSS 对当前页返回空后，后续页通常也是空，停止该排序的翻页
                break
        stats["reviews_by_sort"][sort_by] = len(reviews_for_sort)
        stats["reviews_total"] += len(reviews_for_sort)

    write_json(cache_dir / "collection_notes.json", envelope(app_id, "", stats, fetched_at))
    return stats
