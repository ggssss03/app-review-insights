import unittest

from app_review_insights.llm import MockLLM, parse_json_content


class ParseJsonTest(unittest.TestCase):
    def test_fenced_json(self):
        self.assertEqual(parse_json_content('```json\n{"a": 1}\n```'), {"a": 1})

    def test_noise_around_json(self):
        self.assertEqual(parse_json_content('prefix {"b": 2} suffix'), {"b": 2})

    def test_invalid_raises(self):
        with self.assertRaises(Exception):
            parse_json_content("not json at all")


class MockLLMTest(unittest.TestCase):
    def test_responder_called(self):
        llm = MockLLM(lambda messages: {"ok": True})
        self.assertEqual(llm.chat_json([{"role": "user", "content": "hi"}]), {"ok": True})


if __name__ == "__main__":
    unittest.main()
