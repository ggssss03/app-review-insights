import unittest

from app_review_insights.analysis.planning import generate_requirements, generate_test_cases
from app_review_insights.llm import MockLLM


def findings():
    return [
        {"id": "F-stat-0", "status": "kept", "statement": "s", "evidence_review_ids": ["r1", "r2"], "sample_count": 2},
        {"id": "F-model-0-1", "status": "kept", "statement": "m", "evidence_review_ids": ["r1"], "sample_count": 1},
    ]


class RequirementsTest(unittest.TestCase):
    def test_generated_and_validated(self):
        llm = MockLLM(lambda m: {"requirements": [
            {"code": "R1", "title": "减少广告打扰", "description": "d", "priority": "P1",
             "planned_version": "V1", "finding_ids": ["F-stat-0", "F-not-exist"],
             "review_ids": ["r1", "fake"], "acceptance_criteria": ["c"]},
        ]})
        reqs, note = generate_requirements(findings(), llm=llm)
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0]["finding_ids"], ["F-stat-0"])
        self.assertEqual(reqs[0]["review_ids"], ["r1"])
        self.assertEqual(note, "模型生成")

    def test_without_llm_returns_note(self):
        reqs, note = generate_requirements(findings(), llm=None)
        self.assertEqual(reqs, [])
        self.assertIn("需要 LLM", note)


class TestCaseTest(unittest.TestCase):
    def test_generated_and_validated(self):
        reqs = [{"code": "R1", "priority": "P1", "planned_version": "V1", "title": "t",
                 "description": "d", "review_ids": ["r1"], "finding_ids": ["F-stat-0"]}]
        llm = MockLLM(lambda m: {"test_cases": [
            {"code": "TC1", "title": "验证弹窗", "requirement_ids": ["R1", "R99"],
             "review_ids": ["r1"], "gherkin": {"given": ["打开"], "when": ["点击"], "then": ["看到"]}},
        ]})
        cases, note = generate_test_cases(reqs, llm=llm)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["requirement_ids"], ["R1"])
        self.assertEqual(note, "模型生成")

    def test_without_llm(self):
        cases, note = generate_test_cases([], llm=None)
        self.assertEqual(cases, [])
        self.assertIn("需要 LLM", note)


if __name__ == "__main__":
    unittest.main()
