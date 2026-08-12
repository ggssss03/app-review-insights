import json
import pathlib
import tempfile
import threading
import time
import unittest
import urllib.request

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


if __name__ == "__main__":
    unittest.main()
