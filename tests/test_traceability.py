import unittest

from app_review_insights.analysis.traceability import validate_traceability


class TraceabilityTest(unittest.TestCase):
    def test_happy_path(self):
        reviews = [{"review_key": "r1"}, {"review_key": "r2"}]
        findings = [{"id": "F1", "evidence_review_ids": ["r1", "r2"], "sample_count": 2}]
        requirements = [{"code": "R1", "finding_ids": ["F1"], "review_ids": ["r1"]}]
        test_cases = [{"code": "TC1", "requirement_ids": ["R1"], "review_ids": ["r1"]}]
        result = validate_traceability(reviews, findings, requirements, test_cases)
        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["passed_checks"], 4)

    def test_orphan_finding_removed(self):
        reviews = [{"review_key": "r1"}]
        findings = [{"id": "F1", "evidence_review_ids": ["ghost"]}]
        result = validate_traceability(reviews, findings, [], [])
        self.assertIn("F1", result["removed_findings"])
        self.assertEqual(result["findings"], [])
        self.assertFalse(result["ok"])

    def test_unsupported_requirement_marked_assumption(self):
        reviews = [{"review_key": "r1"}]
        findings = [{"id": "F1", "evidence_review_ids": ["r1"]}]
        requirements = [{"code": "R1", "finding_ids": [], "review_ids": []}]
        result = validate_traceability(reviews, findings, requirements, [])
        self.assertIn("R1", result["assumption_requirements"])
        self.assertEqual(result["requirements"], [])

    def test_test_case_linked_to_removed_requirement_removed(self):
        reviews = [{"review_key": "r1"}]
        findings = [{"id": "F1", "evidence_review_ids": ["r1"]}]
        requirements = [{"code": "R1", "finding_ids": [], "review_ids": []}]
        test_cases = [{"code": "TC1", "requirement_ids": ["R1"]}]
        result = validate_traceability(reviews, findings, requirements, test_cases)
        self.assertIn("TC1", result["removed_test_cases"])


if __name__ == "__main__":
    unittest.main()
