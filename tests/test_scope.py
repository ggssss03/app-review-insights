import unittest

from app_review_insights.analysis.scope import DEFAULT_SCOPE, parse_scope
from app_review_insights.llm import MockLLM


class ScopeTest(unittest.TestCase):
    def test_rule_seed_without_llm(self):
        scope = parse_scope("重点分析订阅转化和付费墙体验")
        self.assertIn("subscription_conversion", scope["focus_areas"])

    def test_default_scope(self):
        scope = parse_scope("")
        self.assertEqual(scope["focus_areas"], DEFAULT_SCOPE["focus_areas"])

    def test_llm_scope(self):
        llm = MockLLM(lambda m: {
            "scope": {
                "focus_areas": ["usability", "performance"],
                "star_filter": {"min": 1, "max": 2},
                "version_filter": "8.5.0",
                "note": "低分可用性",
            }
        })
        scope = parse_scope("低分评论的可用性问题", llm=llm)
        self.assertEqual(scope["focus_areas"], ["performance", "usability"])
        self.assertEqual(scope["star_filter"]["min"], 1)
        self.assertEqual(scope["version_filter"], "8.5.0")

    def test_llm_failure_falls_back(self):
        llm = MockLLM(lambda m: (_ for _ in ()).throw(RuntimeError("boom")))
        scope = parse_scope("订阅转化", llm=llm)
        self.assertIn("subscription_conversion", scope["focus_areas"])
        self.assertIn("失败", scope["note"])


if __name__ == "__main__":
    unittest.main()
