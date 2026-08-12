import json
import pathlib
import re
import tempfile
import unittest

from app_review_insights.analysis.pipeline import run_pipeline
from app_review_insights.llm import MockLLM
from app_review_insights.storage import write_json


def responder(messages):
    content = " ".join(m.get("content", "") for m in messages)
    if "分析目标" in content:
        return {"scope": {
            "focus_areas": ["subscription_conversion"],
            "star_filter": {"min": None, "max": None},
            "version_filter": None,
            "note": "订阅",
        }}
    if "cluster" in content:
        ids = [int(i) for i in re.findall(r"cluster (\d+)", content)]
        return {"topics": [
            {"topic_id": i, "label": f"主题{i}", "description": "描述", "keywords": ["k"]}
            for i in ids
        ]}
    if "样本评论" in content:
        ids = re.findall(r"\[([^\]]+)\]", content)
        return {"findings": [
            {"statement": "用户反馈该主题问题", "evidence_review_ids": ids[:2],
             "confidence": 0.8, "uncertainty": "低", "conflicts": []},
        ]}
    if "带证据的发现" in content:
        fids = re.findall(r"(F-[A-Za-z]+-\d+(?:-\d+)?)", content)
        rids = re.findall(r"\[([^\]]+)\]", content)
        return {"requirements": [
            {"code": "R1", "title": "改进体验", "description": "减少用户负面反馈",
             "priority": "P1", "planned_version": "V1",
             "finding_ids": [fids[0]] if fids else [],
             "review_ids": rids[:2], "acceptance_criteria": ["可验证"]},
        ]}
    if "需求列表" in content:
        return {"test_cases": [
            {"code": "TC1", "title": "验证改进", "requirement_ids": ["R1"],
             "review_ids": [], "gherkin": {"given": ["打开"], "when": ["操作"], "then": ["达成"]}},
        ]}
    return {}


class PipelineTest(unittest.TestCase):
    def test_end_to_end_with_mock_llm(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            raw_dir = base / "raw" / "999999"
            raw_dir.mkdir(parents=True)
            rows = []
            for i in range(6):
                rows.append({
                    "source": "import", "app_id": "999999", "review_id": f"r{i}",
                    "author": f"u{i}", "rating": 2 if i < 3 else 1,
                    "title": "", "body": (
                        "ads popup subscription every minute" if i < 3
                        else "app crashes every time I open it"
                    ),
                    "version": "8.5.0", "country": "us", "updated": f"2026-08-0{i + 1}",
                    "helpful_votes": 0, "page_url": "", "sort_by": "", "fetched_at": "t",
                })
            write_json(raw_dir / "imported-reviews.json", {
                "source": "import", "count": 6, "imported_at": "t", "reviews": rows,
            })
            out_dir = base / "out" / "999999"
            result = run_pipeline(
                app_id="999999",
                raw_dir=raw_dir,
                out_dir=out_dir,
                goal_text="订阅转化",
                llm=MockLLM(responder),
                embed_backend="tfidf",
            )
            summary = result["summary"]
            self.assertEqual(summary["counts"]["reviews"], 6)
            self.assertGreaterEqual(summary["counts"]["topics"], 1)
            self.assertGreaterEqual(summary["counts"]["findings"], 1)
            self.assertGreaterEqual(summary["counts"]["requirements"], 1)
            self.assertGreaterEqual(summary["counts"]["test_cases"], 1)
            self.assertTrue(summary["model_driven"])
            self.assertTrue(summary["traceability"]["passed_checks"] >= 1)
            self.assertTrue((out_dir / "analysis" / "summary.json").exists())
            self.assertTrue((out_dir / "analysis" / "traceability.json").exists())


if __name__ == "__main__":
    unittest.main()
