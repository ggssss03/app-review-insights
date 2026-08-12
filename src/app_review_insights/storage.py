"""文件存储工具：把原始响应与处理结果落盘为 JSON/CSV。"""

from __future__ import annotations

import csv
import json
import pathlib
from typing import Any, Iterable


def ensure_dir(path: pathlib.Path) -> pathlib.Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def envelope(app_id: str, url: str, data: Any, fetched_at: str) -> dict:
    """缓存文件的统一信封，保证每条缓存数据都可溯源。"""
    return {
        "app_id": app_id,
        "url": url,
        "fetched_at": fetched_at,
        "data": data,
    }


def write_json(path: pathlib.Path, obj: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: pathlib.Path, rows: Iterable[dict], fieldnames: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
