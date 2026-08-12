"""核心数据模型（M1 阶段使用 dataclass，后续可平移为 SQLAlchemy/Pydantic）。"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Any, Optional


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


@dataclasses.dataclass
class AppInfo:
    """应用元数据（来自 iTunes Lookup API）。"""

    app_id: str
    track_name: str
    genre: str
    rating_count: int
    avg_rating: float
    version: str
    release_date: str
    minimum_os_version: str
    url: str
    storefront: str
    fetched_at: str
    raw: dict

    @classmethod
    def from_lookup(cls, app_id: str, result: dict, storefront: str = "us",
                    fetched_at: Optional[str] = None) -> "AppInfo":
        genres = result.get("genres") or []
        return cls(
            app_id=str(result.get("trackId", app_id)),
            track_name=_clean_str(result.get("trackName")),
            genre=_clean_str(result.get("primaryGenreName") or (genres[0] if genres else "")),
            rating_count=int(result.get("userRatingCount") or 0),
            avg_rating=float(result.get("averageUserRating") or 0.0),
            version=_clean_str(result.get("version")),
            release_date=_clean_str(result.get("currentVersionReleaseDate")),
            minimum_os_version=_clean_str(result.get("minimumOsVersion")),
            url=_clean_str(result.get("trackViewUrl")),
            storefront=storefront,
            fetched_at=fetched_at or utcnow_iso(),
            raw=result,
        )

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class ReviewRaw:
    """单条原始评论。source 标记来源：rss / import。"""

    source: str
    app_id: str
    review_id: str
    author: str
    rating: int
    title: str
    body: str
    version: str
    country: str
    updated: str
    helpful_votes: int
    page_url: str
    sort_by: str
    fetched_at: str
    raw: dict

    @classmethod
    def create(
        cls,
        *,
        source: str,
        app_id: str,
        review_id: str = "",
        author: str = "",
        rating: int = 0,
        title: str = "",
        body: str = "",
        version: str = "",
        country: str = "us",
        updated: str = "",
        helpful_votes: int = 0,
        page_url: str = "",
        sort_by: str = "",
        raw: Optional[dict] = None,
    ) -> "ReviewRaw":
        return cls(
            source=source,
            app_id=app_id,
            review_id=_clean_str(review_id),
            author=_clean_str(author),
            rating=rating,
            title=_clean_str(title),
            body=_clean_str(body),
            version=_clean_str(version),
            country=_clean_str(country) or "us",
            updated=_clean_str(updated),
            helpful_votes=int(helpful_votes or 0),
            page_url=_clean_str(page_url),
            sort_by=_clean_str(sort_by),
            fetched_at=utcnow_iso(),
            raw=raw or {},
        )

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.pop("raw", None)
        return d
