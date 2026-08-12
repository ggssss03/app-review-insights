"""App Store 数据采集（官方公共接口）。

- 应用元数据：iTunes Lookup API
- 评论数据：iTunes Customer Reviews RSS（美国区 storefront）
不爬页面可见内容；请求间隔 >= delay 秒；原始响应按页缓存，可断点续采。
"""

from __future__ import annotations

import json
import os
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
AMP_PAGE_URL = "https://apps.apple.com/{country}/app/id{app_id}"
AMP_REVIEWS_URL = "https://amp-api.apps.apple.com/v1/catalog/{country}/apps/{app_id}/reviews"
ITML_REVIEWS_URL = "https://itunes.apple.com/WebObjects/MZStore.woa/wa/userReviewsRow"
SORT_ORDERS = ("mostRecent", "mostHelpful")
MAX_PAGES = 10
RSS_RETRIES = 6
RSS_RETRY_DELAY = 1.0
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
USER_AGENT = "app-review-insights/0.1 (local demo collector)"
US_STORE_FRONT = "143441-1,29"
CN_STORE_FRONT = "143465-1,29"
ITML_SORT_IDS = {"mostHelpful": 1, "mostRecent": 4}

REVIEW_ID_PATTERN = re.compile(r"(?:[?&]id=|/id)(\d+)")


def http_get_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get_text(url: str, headers: Optional[dict] = None, timeout: int = 60) -> str:
    merged = {"User-Agent": BROWSER_UA}
    if headers:
        merged.update(headers)
    req = urllib.request.Request(url, headers=merged)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_app_id(url_or_id: str) -> str:
    """从 App Store URL 或裸 id 中提取 app id。"""
    text = url_or_id.strip()
    if text.isdigit():
        return text
    m = REVIEW_ID_PATTERN.search(text)
    if m:
        return m.group(1)
    raise ValueError(f"无法从输入中解析 App Store 应用 id: {url_or_id!r}")


def extract_country(url_or_id: str, default: str = "cn") -> str:
    """从 App Store 链接中识别 storefront 国家；无法识别时返回默认值。

    用户只提供中国区链接（如 https://apps.apple.com/cn/...），按链接国家取数；
    裸 ID 默认走中国区。美国区逻辑仍保留，可通过显式 us 链接或 --country us 使用。
    """
    text = url_or_id.strip().lower()
    m = re.search(r"apps\.apple\.com/([a-z]{2})/", text)
    if m and m.group(1) in {"us", "cn"}:
        return m.group(1)
    return default


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


def storefront_for(country: str) -> str:
    """返回指定国家对应的 X-Apple-Store-Front 值。"""
    return CN_STORE_FRONT if country == "cn" else US_STORE_FRONT


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


def extract_amp_token(html: str) -> str:
    """从应用页面 HTML 中提取 AMP 评论 API 的 Bearer token。"""
    m = re.search(r'"token":"([^"]+)"', html)
    if m:
        return m.group(1)
    idx = html.find("amp-api.apps.apple.com")
    if idx >= 0:
        m2 = re.search(r'"token":"([^"]+)"', html[idx : idx + 3000])
        if m2:
            return m2.group(1)
    raise ValueError("未能在应用页面中找到 AMP API token（可能被地理重定向或接口变更）")


def fetch_amp_token(app_id: str, country: str = "us", timeout: int = 60) -> str:
    url = AMP_PAGE_URL.format(country=country, app_id=app_id)
    html = http_get_text(url, timeout=timeout)
    if os.environ.get("AMP_DEBUG"):
        print(f"[amp-debug] url={url} html_len={len(html)}", flush=True)
        print(f"[amp-debug] amp-api_present={'amp-api.apps.apple.com' in html}", flush=True)
        tokens = re.findall(r'"token":"[^"]{8,}"', html)
        print(f"[amp-debug] token_matches={len(tokens)}", flush=True)
        for t in tokens[:5]:
            idx = html.find(t)
            print(f"[amp-debug] token_ctx={html[max(0, idx - 80):idx + 90]!r}", flush=True)
    return extract_amp_token(html)


def parse_amp_payload(payload: dict, *, source: str, app_id: str, country: str,
                      page_url: str, sort_by: str, fetched_at: str) -> list[ReviewRaw]:
    """解析 AMP 评论接口返回：data[].attributes{rating,title,review,date,version,author}。"""
    reviews = []
    for item in payload.get("data") or []:
        attrs = item.get("attributes") or {}
        reviews.append(ReviewRaw.create(
            source=source,
            app_id=app_id,
            review_id=str(item.get("id") or ""),
            author=str(attrs.get("author") or ""),
            rating=int(attrs.get("rating") or 0),
            title=str(attrs.get("title") or ""),
            body=str(attrs.get("review") or ""),
            version=str(attrs.get("version") or ""),
            country=country,
            updated=str(attrs.get("date") or ""),
            page_url=page_url,
            sort_by=sort_by,
            raw=item,
        ))
    return reviews


def parse_itml_payload(payload: dict, *, source: str, app_id: str, country: str,
                       page_url: str, sort_by: str, fetched_at: str) -> list[ReviewRaw]:
    """解析 WebObjects userReviewsRow 接口返回的评论列表（官方接口，无需 AMP token）。"""
    reviews = []
    for item in payload.get("userReviewList") or []:
        if not isinstance(item, dict):
            continue
        try:
            rating = int(float(item.get("rating") or 0))
        except (TypeError, ValueError):
            rating = 0
        try:
            votes = int(float(item.get("voteSum") or 0))
        except (TypeError, ValueError):
            votes = 0
        reviews.append(ReviewRaw.create(
            source=source,
            app_id=app_id,
            review_id=str(item.get("userReviewId") or ""),
            author=str(item.get("name") or ""),
            rating=rating,
            title=str(item.get("title") or ""),
            body=str(item.get("body") or ""),
            country=country,
            updated=str(item.get("date") or ""),
            helpful_votes=votes,
            page_url=page_url,
            sort_by=sort_by,
            raw=item,
        ))
    return reviews


def parse_amp_page_shelf_reviews(payload: dict, *, source: str, app_id: str, country: str,
                                 page_url: str = "", sort_by: str = "page") -> list[ReviewRaw]:
    """从 App Store 产品页 serialized-server-data 的 allProductReviews shelf 中解析评论。

    苹果在部分 storefront 的产品页中内嵌 8 条真实用户评论（如中国区页面），
    结构为 shelfMapping.allProductReviews.items[].review{id,title,contents,date,rating,reviewerName}。
    """
    reviews = []
    try:
        data = payload["data"][0]["data"]
        shelf = data.get("shelfMapping", {}).get("allProductReviews", {})
        items = shelf.get("items") or []
    except (KeyError, IndexError, TypeError, AttributeError):
        items = []
    for item in items:
        review = (item or {}).get("review") or {}
        if not isinstance(review, dict):
            continue
        try:
            rating = int(float(review.get("rating") or 0))
        except (TypeError, ValueError):
            rating = 0
        reviews.append(ReviewRaw.create(
            source=source,
            app_id=app_id,
            review_id=str(review.get("id") or ""),
            author=str(review.get("reviewerName") or ""),
            rating=rating,
            title=str(review.get("title") or ""),
            body=str(review.get("contents") or ""),
            country=country,
            updated=str(review.get("date") or ""),
            page_url=page_url,
            sort_by=sort_by,
            raw=review,
        ))
    return reviews


def fetch_itml_reviews(
    app_id: str,
    *,
    country: str = "us",
    sort_by: str = "mostRecent",
    cache_dir: pathlib.Path,
    timeout: int = 30,
    refresh: bool = False,
) -> dict:
    """通过 iTunes WebObjects userReviewsRow 接口采集评论。

    这是当前仍然可用的 Apple 官方端点：无需 AMP token、不会被地理重定向，
    返回的评论包含正文/评分/日期/投票数。苹果对该接口的分页参数已不敏感
    （多次实测始终返回同一批热门评论），因此本采集器取一页即可，其余数据
    依赖 GitHub Actions 定时刷新与 JSON/CSV 导入兜底。
    """
    ensure_dir(cache_dir)
    fetched_at = utcnow_iso()
    if country == "cn":
        raise ValueError(
            "itml (userReviewsRow) 接口仅对美国区 storefront 有效；"
            "中国区请使用 rss 方法（cn RSS 仍可用）。"
        )
    sort_id = ITML_SORT_IDS.get(sort_by, 4)
    url = (
        f"{ITML_REVIEWS_URL}?id={urllib.parse.quote(app_id)}"
        f"&displayable-kind=11&sortId={sort_id}&pageNumber=0"
    )
    stats = {
        "app_id": app_id,
        "country": country,
        "method": "itml",
        "fetched_at": fetched_at,
        "pages_fetched": 0,
        "pages_skipped": 0,
        "reviews_total": 0,
        "reviews_by_sort": {},
        "empty_pages": [],
        "errors": [],
        "notes": [
            "数据来源：Apple iTunes WebObjects userReviewsRow 官方接口（2026 年实测仍可用）。",
            "注意：该接口当前只返回同一批热门评论（分页参数已被苹果忽略），"
            "批量数据请使用 GitHub Actions 定时刷新或导入 JSON/CSV。",
        ],
    }
    try:
        info = lookup_app(app_id, country=country, timeout=timeout)
        stats["storefront_ok"] = True
        stats["storefront_app"] = info.track_name
    except Exception as exc:  # noqa: BLE001
        stats["storefront_ok"] = False
        stats["errors"].append({
            "stage": "lookup",
            "error": str(exc),
            "note": f"该应用 ID 在 {country} 区商店不可用或查询失败；"
                    "评论接口仍返回了数据，请人工确认归属后再使用。",
        })
        stats["notes"].append(
            f"注意：该应用 ID 在 {country} 区商店不可用（Lookup 无结果），"
            "返回的评论可能来自其他商店/应用，请核对归属。"
        )
    cache_file = cache_dir / f"reviews-itml-{sort_by}-p0.json"
    if cache_file.exists() and not refresh:
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            stats["pages_skipped"] = 1
        except Exception as exc:  # noqa: BLE001
            stats["errors"].append({"stage": "cache", "error": str(exc)})
            payload = None
    else:
        payload = None
    if payload is None:
        try:
            text = http_get_text(url, headers={
                "Accept": "application/json",
                "X-Apple-Store-Front": storefront_for(country),
            }, timeout=timeout)
            payload = json.loads(text)
            write_json(cache_file, envelope(app_id, url, payload, fetched_at))
            stats["pages_fetched"] = 1
        except Exception as exc:  # noqa: BLE001
            stats["errors"].append({"url": url, "error": str(exc)})
            write_json(cache_dir / "collection_notes.json", envelope(app_id, "", stats, fetched_at))
            return stats
    reviews = parse_itml_payload(
        payload, source="itml", app_id=app_id, country=country,
        page_url=url, sort_by=sort_by, fetched_at=fetched_at,
    )
    stats["reviews_by_sort"][sort_by] = len(reviews)
    stats["reviews_total"] = len(reviews)
    if not reviews:
        stats["empty_pages"].append({"sort_by": sort_by, "page": 0, "url": url})
    write_json(cache_dir / "collection_notes.json", envelope(app_id, "", stats, fetched_at))
    return stats


def fetch_amp_reviews(
    app_id: str,
    *,
    country: str = "us",
    max_reviews: int = 200,
    limit: int = 20,
    delay: float = 1.0,
    cache_dir: pathlib.Path,
    timeout: int = 60,
    refresh: bool = False,
) -> dict:
    """通过 App Store 页面使用的 AMP 评论 API 采集评论（官方接口）。"""
    ensure_dir(cache_dir)
    fetched_at = utcnow_iso()
    stats = {
        "app_id": app_id,
        "country": country,
        "method": "amp",
        "fetched_at": fetched_at,
        "pages_fetched": 0,
        "pages_skipped": 0,
        "reviews_total": 0,
        "reviews_by_offset": {},
        "empty_pages": [],
        "errors": [],
        "notes": [
            "数据来源：Apple AMP Reviews API（App Store 页面使用的官方接口）。",
        ],
    }
    try:
        token = fetch_amp_token(app_id, country=country, timeout=timeout)
        stats["token_ok"] = True
    except Exception as exc:  # noqa: BLE001
        stats["token_ok"] = False
        stats["errors"].append({"stage": "token", "error": str(exc)})
        stats["notes"].append("获取 AMP token 失败（页面被地理重定向或接口变更），"
                              "请使用 GitHub Actions（US runner）或导入 JSON/CSV。")
        write_json(cache_dir / "collection_notes.json", envelope(app_id, "", stats, fetched_at))
        return stats

    offset = 0
    while offset < max_reviews:
        url = (
            f"{AMP_REVIEWS_URL.format(country=country, app_id=app_id)}"
            f"?l=en-US&offset={offset}&limit={limit}&platform=web"
            f"&additionalPlatforms=appletv,ipad,iphone,mac&sort=RELEVANCE"
        )
        cache_file = cache_dir / f"reviews-amp-offset-{offset}.json"
        if cache_file.exists() and not refresh:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            stats["pages_skipped"] += 1
        else:
            try:
                text = http_get_text(url, headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "X-Apple-Store-Front": US_STORE_FRONT,
                }, timeout=timeout)
                payload = json.loads(text)
                write_json(cache_file, envelope(app_id, url, payload, utcnow_iso()))
                stats["pages_fetched"] += 1
                time.sleep(delay)
            except Exception as exc:  # noqa: BLE001
                stats["errors"].append({"url": url, "error": str(exc)})
                break
        reviews = parse_amp_payload(
            payload, source="amp", app_id=app_id, country=country,
            page_url=url, sort_by="relevance", fetched_at=fetched_at,
        )
        stats["reviews_by_offset"][str(offset)] = len(reviews)
        stats["reviews_total"] += len(reviews)
        if not reviews or len(reviews) < limit:
            break
        offset += limit

    write_json(cache_dir / "collection_notes.json", envelope(app_id, "", stats, fetched_at))
    return stats


def fetch_amp_page_reviews(
    app_id: str,
    *,
    country: str = "cn",
    cache_dir: pathlib.Path,
    timeout: int = 90,
    refresh: bool = False,
) -> dict:
    """从 App Store 产品页内嵌的 serialized-server-data 中采集评论（约 8 条）。

    cn RSS 对部分应用（如高评分量级应用）返回空 feed 时使用此兜底：
    苹果在中国区产品页中内嵌真实用户评论，结构为
    shelfMapping.allProductReviews.items[].review。
    """
    ensure_dir(cache_dir)
    fetched_at = utcnow_iso()
    url = AMP_PAGE_URL.format(country=country, app_id=app_id)
    cache_file = cache_dir / "reviews-amp-page-cn.json"
    stats = {
        "app_id": app_id,
        "country": country,
        "method": "amp-page",
        "fetched_at": fetched_at,
        "pages_fetched": 0,
        "pages_skipped": 0,
        "reviews_total": 0,
        "empty_pages": [],
        "errors": [],
        "notes": [
            "数据来源：App Store 中国区产品页内嵌评论（serialized-server-data），"
            "cn RSS 为空时的兜底通道。",
        ],
    }
    if cache_file.exists() and not refresh:
        stats["pages_skipped"] = 1
    else:
        try:
            html = http_get_text(url, timeout=timeout)
            m = re.search(
                r'<script type="application/json" id="serialized-server-data">(.*?)</script>',
                html,
                re.S,
            )
            if not m:
                raise ValueError("产品页中未找到 serialized-server-data")
            payload = json.loads(m.group(1))
            data = payload["data"][0]["data"]
            shelf = (data.get("shelfMapping") or {}).get("allProductReviews") or {}
            items = shelf.get("items") or []
            if not items:
                raise ValueError("产品页内嵌评论为空")
            write_json(cache_file, envelope(app_id, url, {"shelfMapping": data["shelfMapping"]}, fetched_at))
            stats["pages_fetched"] = 1
        except Exception as exc:  # noqa: BLE001
            stats["errors"].append({"url": url, "error": str(exc)})
            write_json(cache_dir / "collection_notes.json", envelope(app_id, "", stats, fetched_at))
            return stats
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        reviews = parse_amp_page_shelf_reviews(
            {"data": [{"data": payload["data"]}]}, source="amp-page",
            app_id=app_id, country=country,
            page_url=url, sort_by="page",
        )
    except Exception as exc:  # noqa: BLE001
        stats["errors"].append({"stage": "parse", "error": str(exc)})
        reviews = []
    stats["reviews_total"] = len(reviews)
    if not reviews:
        stats["empty_pages"].append({"url": url})
    write_json(cache_dir / "collection_notes.json", envelope(app_id, "", stats, fetched_at))
    return stats


def _fetch_rss_reviews(
    app_id: str,
    *,
    country: str = "cn",
    sort_orders: tuple[str, ...] = SORT_ORDERS,
    max_pages: int = MAX_PAGES,
    delay: float = 1.0,
    cache_dir: pathlib.Path,
    timeout: int = 30,
    refresh: bool = False,
) -> dict:
    """Customer Reviews RSS 采集：中国区 cn RSS 仍可用（每页约 35 条），美国区已停用。"""
    ensure_dir(cache_dir)
    fetched_at = utcnow_iso()
    stats = {
        "app_id": app_id,
        "country": country,
        "method": "rss",
        "fetched_at": fetched_at,
        "pages_fetched": 0,
        "pages_skipped": 0,
        "reviews_total": 0,
        "reviews_by_sort": {},
        "empty_pages": [],
        "errors": [],
        "notes": [
            f"数据来源：Apple iTunes Customer Reviews RSS（{country} 区）。",
            "注意：美国区 RSS 已被苹果停用（返回空 feed）；"
            "中国区 cn RSS 实测仍可用（每页约 35 条，仅第一页有数据）。",
        ],
    }
    for sort_by in sort_orders:
        reviews_for_sort = []
        for page in range(1, max_pages + 1):
            url = build_rss_url(app_id, sort_by, page, country=country)
            cache_file = cache_dir / f"reviews-{sort_by}-p{page}.json"
            if cache_file.exists() and not refresh:
                payload = json.loads(cache_file.read_text(encoding="utf-8"))
                stats["pages_skipped"] += 1
            else:
                payload = None
                for attempt in range(1, RSS_RETRIES + 1):
                    try:
                        candidate = http_get_json(url, timeout=timeout)
                        candidate_entries = (
                            candidate.get("feed", {}).get("entry") or []
                        )
                        if isinstance(candidate_entries, dict):
                            candidate_entries = [candidate_entries]
                        if candidate_entries or attempt == RSS_RETRIES:
                            payload = candidate
                            break
                    except Exception as exc:  # noqa: BLE001
                        stats["errors"].append({"url": url, "attempt": attempt, "error": str(exc)})
                    time.sleep(RSS_RETRY_DELAY)
                if payload is None:
                    stats["errors"].append({"url": url, "error": "RSS 多次重试仍失败"})
                    break
                write_json(cache_file, envelope(app_id, url, payload, fetched_at))
                stats["pages_fetched"] += 1
                time.sleep(delay)
            reviews = parse_review_feed(
                payload, source="rss", app_id=app_id, country=country,
                page_url=url, sort_by=sort_by, fetched_at=fetched_at,
            )
            reviews_for_sort.extend(reviews)
            if not reviews:
                stats["empty_pages"].append({"sort_by": sort_by, "page": page, "url": url})
                break
        stats["reviews_by_sort"][sort_by] = len(reviews_for_sort)
        stats["reviews_total"] += len(reviews_for_sort)

    write_json(cache_dir / "collection_notes.json", envelope(app_id, "", stats, fetched_at))
    return stats


def _merge_cached_reviews(
    app_id: str,
    *,
    cache_dir: pathlib.Path,
    rss_stats: dict,
    page_stats: dict,
    us_stats: dict,
) -> dict:
    """统计缓存目录中多来源评论的合并唯一数（RSS + 产品页 + 美国区 itml）。"""
    fetched_at = utcnow_iso()
    seen: set[str] = set()
    by_source: dict[str, int] = {}
    notes = list(rss_stats.get("notes", []))
    notes.append(
        "中国区采集为多源合并：cn RSS（重试）+ 产品页内嵌评论 + 美国区 itml，"
        "去重后为分析输入。"
    )
    errors = list(rss_stats.get("errors", []))
    for stats, tag in ((rss_stats, "rss"), (page_stats, "amp-page"), (us_stats, "itml")):
        if stats.get("errors"):
            errors.extend(stats["errors"])
    for file in sorted(cache_dir.glob("reviews-*.json")):
        if file.name == "collection_notes.json":
            continue
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))
            data = payload.get("data") or payload
            source = "rss"
            if "amp-page" in file.name:
                source = "amp-page"
            elif "itml" in file.name:
                source = "itml"
            entries = []
            if isinstance(data, dict):
                if "amp-page" in file.name:
                    shelf = data.get("shelfMapping") or {}
                    items = (shelf.get("allProductReviews") or {}).get("items") or []
                    entries = [((it or {}).get("review") or {}) for it in items]
                    for entry in entries:
                        rid = str(entry.get("id") or "")
                        if rid and rid not in seen:
                            seen.add(rid)
                            by_source[source] = by_source.get(source, 0) + 1
                    continue
                feed = data.get("feed") or {}
                entries = feed.get("entry") or []
                if isinstance(entries, dict):
                    entries = [entries]
                if isinstance(data.get("userReviewList"), list):
                    entries = data["userReviewList"]
            for entry in entries:
                rid = ""
                if isinstance(entry, dict):
                    review = entry.get("review")
                    if isinstance(review, dict):
                        rid = str(review.get("id") or "")
                    rid = str(
                        rid
                        or entry.get("userReviewId")
                        or (entry.get("id") or {}).get("label", "")
                        or entry.get("id", "")
                    )
                if rid and rid not in seen:
                    seen.add(rid)
                    by_source[source] = by_source.get(source, 0) + 1
        except Exception:  # noqa: BLE001
            continue
    write_json(cache_dir / "collection_notes.json", envelope(app_id, "", {
        "app_id": app_id,
        "country": "cn",
        "method": "merged",
        "fetched_at": fetched_at,
        "reviews_total": len(seen),
        "reviews_unique": len(seen),
        "reviews_by_source": by_source,
        "errors": errors,
        "notes": notes,
    }, fetched_at))
    return {
        "app_id": app_id,
        "country": "cn",
        "method": "merged",
        "fetched_at": fetched_at,
        "pages_fetched": 0,
        "pages_skipped": 0,
        "reviews_total": len(seen),
        "reviews_by_source": by_source,
        "empty_pages": [],
        "errors": errors,
        "notes": notes,
    }


def fetch_reviews(
    app_id: str,
    *,
    country: str = "cn",
    sort_orders: tuple[str, ...] = SORT_ORDERS,
    max_pages: int = MAX_PAGES,
    delay: float = 1.0,
    cache_dir: pathlib.Path,
    timeout: int = 30,
    refresh: bool = False,
    method: str = "auto",
) -> dict:
    """Collect reviews by storefront country.

    中国区（默认）：rss（cn RSS 间歇可用，自动重试）→ 产品页内嵌评论 → 美国区 itml
    多源合并，最大化真实评论数量（通常 35+）；美国区：itml → amp → rss 兜底。
    """
    if country == "cn":
        if method == "itml":
            raise ValueError("itml 接口仅支持美国区；中国区请使用 rss 方法。")
        if method == "rss":
            return _fetch_rss_reviews(
                app_id, country=country, sort_orders=sort_orders, max_pages=max_pages,
                delay=delay, cache_dir=cache_dir, timeout=timeout, refresh=refresh,
            )
        rss_stats = _fetch_rss_reviews(
            app_id, country=country, sort_orders=sort_orders, max_pages=max_pages,
            delay=delay, cache_dir=cache_dir, timeout=timeout, refresh=refresh,
        )
        page_stats = fetch_amp_page_reviews(
            app_id, country=country, cache_dir=cache_dir, timeout=90, refresh=refresh,
        )
        us_stats = {}
        try:
            us_stats = fetch_itml_reviews(
                app_id, country="us", cache_dir=cache_dir,
                timeout=timeout, refresh=refresh,
            )
        except Exception as exc:  # noqa: BLE001
            us_stats = {"reviews_total": 0, "errors": [{"stage": "itml-us", "error": str(exc)}]}
        merged = _merge_cached_reviews(
            app_id, cache_dir=cache_dir, rss_stats=rss_stats,
            page_stats=page_stats, us_stats=us_stats,
        )
        if merged["reviews_total"] == 0:
            merged["notes"].append(
                "cn RSS / 产品页 / 美国区 itml 均为空；请导入 JSON/CSV 数据集。"
            )
        return merged
    if method == "itml":
        return fetch_itml_reviews(
            app_id, country=country, cache_dir=cache_dir,
            timeout=timeout, refresh=refresh,
        )
    if method == "amp":
        return fetch_amp_reviews(
            app_id, country=country, delay=delay, cache_dir=cache_dir,
            timeout=timeout, refresh=refresh,
        )
    if method == "rss":
        return _fetch_rss_reviews(
            app_id, country=country, sort_orders=sort_orders, max_pages=max_pages,
            delay=delay, cache_dir=cache_dir, timeout=timeout, refresh=refresh,
        )
    itml_stats = fetch_itml_reviews(
        app_id, country=country, cache_dir=cache_dir,
        timeout=timeout, refresh=refresh,
    )
    if itml_stats["reviews_total"] > 0:
        return itml_stats
    amp_stats = fetch_amp_reviews(
        app_id, country=country, delay=delay, cache_dir=cache_dir,
        timeout=timeout, refresh=refresh,
    )
    if amp_stats["reviews_total"] > 0:
        itml_stats["notes"].append("ITML empty; AMP fallback succeeded.")
        return amp_stats
    rss_stats = _fetch_rss_reviews(
        app_id, country=country, sort_orders=sort_orders, max_pages=1,
        delay=delay, cache_dir=cache_dir, timeout=timeout, refresh=refresh,
    )
    itml_stats["notes"].append("ITML and AMP both empty; tried legacy RSS.")
    itml_stats["errors"].extend(amp_stats["errors"])
    itml_stats["errors"].extend(rss_stats["errors"])
    return itml_stats
