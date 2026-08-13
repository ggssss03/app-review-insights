"""零第三方依赖的本地 Web 服务器：静态 UI + 分析 API（纯标准库）。

启动：
    python app/server.py [--port 8765] [--data-root data]
打开 http://127.0.0.1:8765 即可使用。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app_review_insights import __version__  # noqa: E402
from app_review_insights.analysis.pipeline import run_pipeline  # noqa: E402
from app_review_insights.collector import (  # noqa: E402
    extract_app_id,
    extract_country,
    fetch_reviews,
    lookup_app,
)
from app_review_insights.config import llm_available, llm_settings, load_dotenv  # noqa: E402
from app_review_insights.importer import import_reviews  # noqa: E402
from app_review_insights.llm import LLMClient  # noqa: E402
from app_review_insights.loader import load_raw_reviews  # noqa: E402
from app_review_insights.storage import write_json  # noqa: E402

STATIC_DIR = pathlib.Path(__file__).resolve().parent / "static"
STATIC_FILES = {"index.html", "app.js", "style.css"}
ANALYSIS_STAGES = {"raw", "scope", "clean", "topics", "findings", "requirements", "testcases", "traceability", "summary", "progress"}


def build_llm() -> Optional[LLMClient]:
    load_dotenv(PROJECT_ROOT / ".env")
    if not llm_available():
        return None
    return LLMClient(**llm_settings())


class ServerApp:
    """持有数据根目录与运行状态，便于测试与复用。"""

    def __init__(self, data_root: pathlib.Path):
        self.data_root = data_root
        self.state: dict[str, dict] = {}
        self._lock = threading.Lock()

    def raw_dir(self, app_id: str) -> pathlib.Path:
        return self.data_root / "raw" / app_id

    def out_dir(self, app_id: str) -> pathlib.Path:
        return self.data_root / "processed" / app_id

    def has_reviews(self, app_id: str) -> bool:
        raw_dir = self.raw_dir(app_id)
        if not raw_dir.exists():
            return False
        return any(
            f.suffix == ".json"
            and f.name not in ("app.json", "collection_notes.json")
            for f in raw_dir.iterdir()
        )

    def start_analyze(self, payload: dict) -> dict:
        raw_value = str(payload.get("url") or payload.get("app_id") or "").strip()
        if not raw_value:
            raise ValueError("需要提供 App Store 链接或 app id")
        app_id = extract_app_id(raw_value)
        country = extract_country(raw_value)
        run_id = f"{app_id}-{int(time.time() * 1000)}"
        with self._lock:
            self.state[run_id] = {
                "run_id": run_id,
                "app_id": app_id,
                "country": country,
                "status": "pending",
                "progress": [],
                "error": None,
            }
        goal = str(payload.get("goal") or "").strip()
        use_llm = bool(payload.get("llm", True))
        fresh = bool(payload.get("fresh", False))
        embed_backend = str(payload.get("embed_backend") or "auto")
        thread = threading.Thread(
            target=self._run,
            args=(run_id, app_id, country, goal, use_llm, embed_backend, fresh),
            daemon=True,
        )
        thread.start()
        return {"run_id": run_id, "app_id": app_id, "country": country, "status": "pending"}

    def _run(self, run_id: str, app_id: str, country: str, goal: str,
             use_llm: bool, embed_backend: str, fresh: bool = False) -> None:
        entry = self.state[run_id]
        entry["status"] = "running"
        try:
            if not self._collect(app_id, country, entry, fresh=fresh):
                return
            llm = build_llm() if use_llm else None
            result = run_pipeline(
                app_id=app_id,
                raw_dir=self.raw_dir(app_id),
                out_dir=self.out_dir(app_id),
                goal_text=goal,
                llm=llm,
                embed_backend=embed_backend,
                force=fresh,
                progress=entry["progress"],
            )
            entry["status"] = "done"
            entry["result"] = result["summary"]
        except Exception as exc:  # noqa: BLE001
            entry["status"] = "error"
            entry["error"] = str(exc)
            entry["progress"].append({"stage": "pipeline", "status": "error", "detail": str(exc)})

    def _collect(self, app_id: str, country: str, entry: dict, *, fresh: bool) -> bool:
        """确保有可用评论；fresh=True 时强制重新采集，成功后覆盖旧原始数据。"""
        if not fresh and self.has_reviews(app_id):
            return True
        raw = self.raw_dir(app_id)
        if fresh:
            entry["progress"].append({
                "stage": "fetch", "status": "running", "detail": "正在重新采集评论（将覆盖旧缓存）",
            })
            # 先写入临时目录：成功才替换旧数据；失败则旧数据原样保留
            with tempfile.TemporaryDirectory() as td:
                stats = fetch_reviews(
                    app_id,
                    country=country,
                    delay=1.0,
                    cache_dir=pathlib.Path(td),
                    refresh=True,
                )
                if stats.get("reviews_total", 0) == 0:
                    entry["progress"].append({
                        "stage": "fetch",
                        "status": "error",
                        "detail": "重新采集未获取到评论（cn RSS/产品页/AMP 均为空），已保留原缓存",
                    })
                    entry["status"] = "error"
                    entry["error"] = "未获取到新评论：请稍后重试或导入 JSON/CSV 数据集（原数据未改动）"
                    return False
                raw.mkdir(parents=True, exist_ok=True)
                for old in list(raw.glob("reviews-*.json")) + [raw / "collection_notes.json"]:
                    if old.exists():
                        old.unlink()
                for new in pathlib.Path(td).glob("reviews-*.json"):
                    shutil.move(str(new), raw / new.name)
                shutil.move(str(pathlib.Path(td) / "collection_notes.json"), raw / "collection_notes.json")
            entry["progress"].append({
                "stage": "fetch",
                "status": "ok",
                "detail": f"重新采集完成（{country} 区），新数据已覆盖旧缓存",
            })
            return True

        # 没有缓存评论时尝试在线采集（需要可访问 Apple 接口的网络）
        entry["progress"].append({"stage": "fetch", "status": "running", "detail": "尝试在线采集评论"})
        stats = fetch_reviews(
            app_id,
            country=country,
            delay=1.0,
            cache_dir=raw,
        )
        if stats.get("reviews_total", 0) == 0:
            entry["progress"].append({
                "stage": "fetch",
                "status": "error",
                "detail": "在线采集完成但未获取到评论（cn RSS/产品页/AMP 均为空），请稍后重试或导入 JSON/CSV",
            })
            entry["status"] = "error"
            entry["error"] = "未获取到评论：请稍后重试（采集源可能临时不可用）或导入 JSON/CSV 数据集"
            return False
        entry["progress"].append({
            "stage": "fetch",
            "status": "ok",
            "detail": f"在线采集完成（{country} 区）",
        })
        return True

    def import_content(self, app_id: str, content: str, fmt: str) -> dict:
        if not app_id.isdigit():
            raise ValueError("app_id 必须是数字")
        suffix = ".csv" if fmt == "csv" else ".json"
        tmp = self.data_root / ".tmp" / f"{app_id}-{int(time.time() * 1000)}{suffix}"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(content, encoding="utf-8")
        reviews = import_reviews(tmp, app_id=app_id)
        out = self.raw_dir(app_id) / "imported-reviews.json"
        write_json(out, {
            "source": "import",
            "count": len(reviews),
            "imported_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "reviews": [r.to_dict() for r in reviews],
        })
        tmp.unlink(missing_ok=True)
        return {"app_id": app_id, "count": len(reviews), "path": str(out)}

    def artifacts(self, app_id: str, stage: str) -> dict:
        if stage not in ANALYSIS_STAGES:
            raise ValueError(f"未知阶段：{stage}")
        if stage == "raw":
            reviews = load_raw_reviews(self.raw_dir(app_id), app_id)
            return {
                "app_id": app_id,
                "stage": stage,
                "data": [r.to_dict() for r in reviews],
            }
        path = self.out_dir(app_id) / "analysis" / f"{stage}.json"
        if not path.exists():
            return {"app_id": app_id, "stage": stage, "error": "该阶段产物不存在", "data": None}
        data = json.loads(path.read_text(encoding="utf-8"))
        # pipeline 将 (列表, 生成说明) 以 [list, note] 形式落盘以保留来源说明；
        # 前端按平铺列表渲染，这里归一化为列表，说明信息保留在 summary 的 notes 中。
        if (
            isinstance(data, list)
            and len(data) == 2
            and isinstance(data[0], list)
            and isinstance(data[1], str)
        ):
            data = data[0]
        return {"app_id": app_id, "stage": stage, "data": data}


class Handler(BaseHTTPRequestHandler):
    server_version = f"app-review-insights/{__version__}"

    @property
    def app(self) -> ServerApp:
        return self.server.app  # type: ignore[attr-defined]

    def _send_json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, name: str) -> None:
        if name not in STATIC_FILES:
            self._send_json({"error": "not found"}, status=404)
            return
        path = STATIC_DIR / name
        body = path.read_bytes()
        ctype = {
            "index.html": "text/html; charset=utf-8",
            "app.js": "text/javascript; charset=utf-8",
            "style.css": "text/css; charset=utf-8",
        }[name]
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parts = urllib.parse.urlsplit(self.path)
        path = parts.path.strip("/")
        query = urllib.parse.parse_qs(parts.query)
        try:
            if path in ("", "index.html"):
                self._send_static("index.html")
            elif path == "app.js":
                self._send_static("app.js")
            elif path == "style.css":
                self._send_static("style.css")
            elif path == "api/health":
                self._send_json({"ok": True, "version": __version__, "llm_available": build_llm() is not None})
            elif path.startswith("api/status/"):
                run_id = path.split("/")[-1]
                entry = self.app.state.get(run_id)
                if entry is None:
                    self._send_json({"error": "run not found"}, status=404)
                else:
                    self._send_json(entry)
            elif path.startswith("api/artifacts/"):
                app_id = path.split("/")[-1]
                stage = query.get("stage", ["summary"])[0]
                self._send_json(self.app.artifacts(app_id, stage))
            elif path.startswith("api/apps/"):
                app_id = path.split("/")[-1]
                meta = self.app.raw_dir(app_id) / "app.json"
                if meta.exists():
                    self._send_json(json.loads(meta.read_text(encoding="utf-8")))
                else:
                    self._send_json({"error": "no metadata"}, status=404)
            else:
                self._send_json({"error": "not found"}, status=404)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)}, status=500)

    def do_POST(self) -> None:  # noqa: N802
        parts = urllib.parse.urlsplit(self.path)
        path = parts.path.strip("/")
        query = urllib.parse.parse_qs(parts.query)
        try:
            if path == "api/analyze":
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                self._send_json(self.app.start_analyze(payload))
            elif path == "api/import":
                app_id = query.get("app_id", [""])[0]
                ctype = self.headers.get("Content-Type", "")
                fmt = "csv" if "csv" in ctype else "json"
                length = int(self.headers.get("Content-Length", 0))
                content = self.rfile.read(length).decode("utf-8") if length else ""
                self._send_json(self.app.import_content(app_id, content, fmt))
            elif path == "api/ask":
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                llm = build_llm()
                if llm is None:
                    self._send_json({"error": "未配置 LLM，无法追问/挑战"}, status=400)
                else:
                    from app_review_insights.prompts import ask_messages, challenge_messages

                    mode = str(payload.get("mode") or "qa")
                    if mode == "challenge":
                        messages = challenge_messages(
                            str(payload.get("statement") or ""),
                            str(payload.get("review_text") or ""),
                            payload.get("review_ids") or [],
                        )
                    else:
                        messages = ask_messages(
                            str(payload.get("question") or ""),
                            str(payload.get("context") or ""),
                            payload.get("review_ids") or [],
                        )
                    self._send_json({"data": llm.chat_json(messages)})
            else:
                self._send_json({"error": "not found"}, status=404)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)}, status=400)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), format % args))


class AppServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, app: ServerApp):
        super().__init__(address, Handler)
        self.app = app


def main() -> int:
    parser = argparse.ArgumentParser(description="App Review Insights 本地 Web UI")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-root", default=str(PROJECT_ROOT / "data"))
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    app = ServerApp(pathlib.Path(args.data_root))
    server = AppServer(("127.0.0.1", args.port), app)
    url = f"http://127.0.0.1:{args.port}"
    print(f"App Review Insights 已启动：{url}")
    print(f"数据目录：{args.data_root}（LLM 可用：{build_llm() is not None}）")
    if not args.no_browser:
        import webbrowser

        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
