import json
import unittest
from unittest.mock import patch

from app_review_insights.llm import LLMClient, MockLLM, parse_json_content


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


class EmptyContentRetryTest(unittest.TestCase):
    def test_empty_content_is_retried(self):
        calls = {"n": 0}

        class FakeResp:
            def __init__(self, body):
                self._body = body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self._body

        def fake_urlopen(req, timeout=60):
            calls["n"] += 1
            if calls["n"] == 1:
                body = {"choices": [{"message": {"content": ""}}]}
            else:
                body = {"choices": [{"message": {"content": '{"ok": true}'}}]}
            return FakeResp(json.dumps(body).encode("utf-8"))

        client = LLMClient(api_key="test-key", max_retries=2)
        with patch("app_review_insights.llm.urllib.request.urlopen", side_effect=fake_urlopen), \
                patch("app_review_insights.llm.time.sleep"):
            result = client.chat_json([{"role": "user", "content": "hi"}])
        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls["n"], 2)


if __name__ == "__main__":
    unittest.main()
