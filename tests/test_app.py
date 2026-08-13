import json
import pathlib
import tempfile
import threading
import time
import unittest
import urllib.request

import app.server as server
from app.server import AppServer, ServerApp


def http_json(url: str, method: str = "GET", body: bytes | None = None, ctype: str = "application/json"):
    req = urllib.request.Request(url, data=body, method=method)
    if body is not None:
        req.add_header("Content-Type", ctype)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


class ServerIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = ServerApp(pathlib.Path(self.tmp.name))
        self.server = AppServer(("127.0.0.1", 0), self.app)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def test_health(self):
        data = http_json(f"http://127.0.0.1:{self.port}/api/health")
        self.assertTrue(data["ok"])
        self.assertIn("llm_available", data)

    def test_index_served(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=10) as resp:
            html = resp.read().decode("utf-8")
        self.assertIn("App Review Insights", html)

    def test_import_analyze_artifacts(self):
        base = f"http://127.0.0.1:{self.port}"
        csv_content = (
            "id,author,rating,content,date\n"
            "s1,Alice,2,ads popup subscription every minute,2026-08-01\n"
            "s2,Bob,2,another subscription popup,2026-08-02\n"
            "s3,Carol,1,app crashes on startup,2026-08-03\n"
            "s4,Dan,1,crash when opening workout,2026-08-04\n"
        )
        imported = http_json(
            f"{base}/api/import?app_id=888001",
            method="POST",
            body=csv_content.encode("utf-8"),
            ctype="text/csv",
        )
        self.assertEqual(imported["count"], 4)

        run = http_json(f"{base}/api/analyze", method="POST", body=json.dumps({
            "app_id": "888001", "goal": "低分可用性", "llm": False, "embed_backend": "tfidf",
        }).encode("utf-8"))
        run_id = run["run_id"]

        status = None
        deadline = time.time() + 20
        while time.time() < deadline:
            status = http_json(f"{base}/api/status/{run_id}")
            if status["status"] in ("done", "error"):
                break
            time.sleep(0.2)
        self.assertEqual(status["status"], "done", status.get("error"))
        self.assertTrue(status["progress"])

        topics = http_json(f"{base}/api/artifacts/888001?stage=topics")["data"]
        self.assertGreaterEqual(len(topics["topics"]), 1)
        summary = http_json(f"{base}/api/artifacts/888001?stage=summary")["data"]
        self.assertEqual(summary["counts"]["reviews"], 4)
        self.assertFalse(summary["model_driven"])


    def test_artifacts_normalizes_list_note_format(self):
        base = f"http://127.0.0.1:{self.port}"
        raw = pathlib.Path(self.tmp.name) / "raw" / "888002"
        out = pathlib.Path(self.tmp.name) / "processed" / "888002" / "analysis"
        raw.mkdir(parents=True, exist_ok=True)
        out.mkdir(parents=True, exist_ok=True)
        (raw / "reviews.json").write_text(json.dumps([{
            "id": "r1", "author": "A", "rating": 3, "title": "T", "content": "B", "date": "2026-01-01",
        }]), encoding="utf-8")
        (out / "requirements.json").write_text(json.dumps([
            [{"code": "R1", "title": "需求一", "priority": "P1", "planned_version": "V1",
              "finding_ids": [], "review_ids": [], "acceptance_criteria": ["标准一"]}],
            "模型生成",
        ], ensure_ascii=False), encoding="utf-8")
        (out / "testcases.json").write_text(json.dumps([
            [{"code": "TC1", "title": "用例一", "requirement_ids": ["R1"], "review_ids": [],
              "gherkin": {"given": ["已安装"], "when": ["点击开始"], "then": ["进入训练"]}}],
            "模型生成",
        ], ensure_ascii=False), encoding="utf-8")
        requirements = http_json(f"{base}/api/artifacts/888002?stage=requirements")["data"]
        self.assertIsInstance(requirements, list)
        self.assertEqual(requirements[0]["code"], "R1")
        self.assertIsInstance(requirements[0], dict)
        testcases = http_json(f"{base}/api/artifacts/888002?stage=testcases")["data"]
        self.assertIsInstance(testcases, list)
        self.assertEqual(testcases[0]["gherkin"]["given"], ["已安装"])


class FreshCollectTest(unittest.TestCase):
    """重新采集（不采用缓存）逻辑：成功覆盖旧数据，失败保留旧数据。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = ServerApp(pathlib.Path(self.tmp.name))
        self._orig_fetch = server.fetch_reviews

    def tearDown(self):
        server.fetch_reviews = self._orig_fetch
        self.tmp.cleanup()

    def test_fresh_replaces_old_raw_and_failure_keeps_old(self):
        raw = self.app.raw_dir("123456")
        raw.mkdir(parents=True, exist_ok=True)
        old = raw / "reviews-mostRecent-p1.json"
        old.write_text(json.dumps({"old": True}), encoding="utf-8")

        def fake_ok(app_id, **kw):
            cache_dir = pathlib.Path(kw["cache_dir"])
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / "reviews-mostRecent-p1.json").write_text(
                json.dumps({"fresh": True}), encoding="utf-8")
            (cache_dir / "collection_notes.json").write_text(
                json.dumps({"reviews_total": 1}), encoding="utf-8")
            return {"reviews_total": 1}

        server.fetch_reviews = fake_ok
        entry = {"status": "pending", "progress": []}
        self.assertTrue(self.app._collect("123456", "cn", entry, fresh=True))
        fresh = raw / "reviews-mostRecent-p1.json"
        self.assertTrue(fresh.exists())
        self.assertEqual(json.loads(fresh.read_text(encoding="utf-8")), {"fresh": True})
        self.assertTrue((raw / "collection_notes.json").exists())
        self.assertEqual(entry["progress"][-1]["status"], "ok")

        # 采集失败：不得删除旧数据，状态置为 error
        old2 = raw / "reviews-mostRecent-p2.json"
        old2.write_text(json.dumps({"old2": True}), encoding="utf-8")
        server.fetch_reviews = lambda app_id, **kw: {"reviews_total": 0}
        entry2 = {"status": "running", "progress": []}
        self.assertFalse(self.app._collect("123456", "cn", entry2, fresh=True))
        self.assertEqual(entry2["status"], "error")
        self.assertTrue(old2.exists())
        self.assertTrue(fresh.exists())


if __name__ == "__main__":
    unittest.main()
