"""M5 场景测试：混合语言 / 证据不足 / 模型失败 / 重复与冲突。"""

import json
import pathlib
import tempfile
import unittest

from app_review_insights.analysis.pipeline import run_pipeline
from app_review_insights.llm import MockLLM
from app_review_insights.storage import write_json


def make_dataset(tmp: pathlib.Path, app_id: str, rows: list[dict]) -> pathlib.Path:
    raw_dir = tmp / "raw" / app_id
    raw_dir.mkdir(parents=True)
    write_json(raw_dir / "imported-reviews.json", {
        "source": "import", "count": len(rows), "imported_at": "t", "reviews": rows,
    })
    return raw_dir


def row(i: int, body: str, rating: int, *, author: str = "u", updated: str = "2026-08-01",
        review_id: str | None = None) -> dict:
    return {
        "source": "import", "app_id": "888999", "review_id": review_id or f"r{i}",
        "author": author, "rating": rating, "title": "", "body": body,
        "version": "1.0", "country": "us", "updated": updated, "helpful_votes": 0,
        "page_url": "", "sort_by": "", "fetched_at": "t",
    }


class ScenarioTest(unittest.TestCase):
    def _run(self, tmp: pathlib.Path, rows: list[dict], llm=None):
        raw_dir = make_dataset(tmp, "888999", rows)
        return run_pipeline(
            app_id="888999",
            raw_dir=raw_dir,
            out_dir=tmp / "out" / "888999",
            goal_text="",
            llm=llm,
            embed_backend="tfidf",
        )

    def test_mixed_language(self):
        rows = [
            row(i, "订阅太贵了，试用结束就自动扣费", 2, author=f"u{i}", updated=f"2026-08-0{i + 1}") for i in range(3)
        ] + [
            row(i + 3, "Too many ads and popups, annoying", 1, author=f"u{i + 3}", updated=f"2026-08-0{i + 4}") for i in range(3)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(pathlib.Path(tmp), rows)
        langs = result["summary"]["clean_stats"]["language_distribution"]
        self.assertIn("zh", langs)
        self.assertIn("en", langs)
        self.assertEqual(result["summary"]["counts"]["reviews"], 6)

    def test_insufficient_evidence(self):
        rows = [row(0, "app keeps crashing", 1)]
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(pathlib.Path(tmp), rows)
        findings = result["summary"]["counts"]["findings"]
        self.assertGreaterEqual(findings, 1)
        trace = result["summary"]["traceability"]
        self.assertGreaterEqual(trace["passed_checks"], 1)

    def test_model_failure_graceful(self):
        rows = [
            row(i, "ads popup subscription", 2, updated=f"2026-08-0{i + 1}") for i in range(3)
        ] + [
            row(i + 3, "app crashes on launch", 1, updated=f"2026-08-0{i + 4}") for i in range(3)
        ]
        failing = MockLLM(lambda m: (_ for _ in ()).throw(RuntimeError("offline")))
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(pathlib.Path(tmp), rows, llm=failing)
        summary = result["summary"]
        self.assertEqual(summary["status"] if "status" in summary else "done", "done")
        self.assertEqual(summary["counts"]["requirements"], 0)
        self.assertGreaterEqual(summary["counts"]["findings"], 1)
        self.assertTrue(any("LLM" in n or "失败" in n for n in summary["notes"]))

    def test_duplicates_and_conflicts(self):
        rows = [
            row(0, "love the workouts, great app", 5, author="A"),
            row(1, "love the workouts, great app", 5, author="A", review_id="dup-1"),
            row(2, "hate the ads, too intrusive", 1, author="B"),
            row(3, "another positive review here", 5, author="C"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(pathlib.Path(tmp), rows)
        clean = result["summary"]["clean_stats"]
        self.assertEqual(clean["unique_count"], 3)
        self.assertEqual(clean["removed_duplicates"], 1)
        with tempfile.TemporaryDirectory() as tmp2:
            self._run(pathlib.Path(tmp2), rows)
            # 冲突：主题内同时存在 1 星与 5 星
            findings_path = pathlib.Path(tmp2) / "out" / "888999" / "analysis" / "findings.json"
            findings = json.loads(findings_path.read_text(encoding="utf-8"))
            self.assertTrue(any(f.get("conflicts") for f in findings if f["provenance"] == "stat"))


if __name__ == "__main__":
    unittest.main()
