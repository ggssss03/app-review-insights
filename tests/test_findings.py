import unittest

from app_review_insights.analysis.findings import build_findings
from app_review_insights.llm import MockLLM


def reviews(n=4):
    return [
        {"review_key": f"r{i}", "title": "", "body": f"text {i}", "text": f"text {i}",
         "rating": 2 if i < 2 else 5, "version": "1.0", "helpful_votes": i}
        for i in range(n)
    ]


def topics_with(review_keys):
    return {
        "memberships": [{"review_key": k, "topic_id": 0} for k in review_keys],
        "topics": [{"topic_id": 0, "label": "测试主题"}],
    }


class FindingsTest(unittest.TestCase):
    def test_stat_only_without_llm(self):
        data = reviews()
        result = build_findings(data, topics_with([r["review_key"] for r in data]), llm=None)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["provenance"], "stat")
        self.assertEqual(result[0]["sample_count"], 4)

    def test_model_findings_citation_whitelist(self):
        data = reviews(6)
        llm = MockLLM(lambda m: {"findings": [
            {"statement": "有效结论", "evidence_review_ids": ["r0", "r1", "fake-id"], "confidence": 1.2, "uncertainty": "", "conflicts": []},
            {"statement": "无引用结论", "evidence_review_ids": [], "confidence": 0.9, "uncertainty": "", "conflicts": []},
        ]})
        result = build_findings(data, topics_with([r["review_key"] for r in data]), llm=llm)
        model_findings = [f for f in result if f["provenance"] == "model"]
        self.assertEqual(len(model_findings), 1)
        self.assertEqual(model_findings[0]["evidence_review_ids"], ["r0", "r1"])
        self.assertEqual(model_findings[0]["confidence"], 1.0)  # clamp

    def test_conflict_detected_on_mixed_ratings(self):
        data = reviews(4)  # 2 低分 + 2 高分
        result = build_findings(data, topics_with([r["review_key"] for r in data]), llm=None)
        self.assertTrue(result[0]["conflicts"])


if __name__ == "__main__":
    unittest.main()
