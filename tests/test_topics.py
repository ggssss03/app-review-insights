import unittest

from app_review_insights.analysis.topics import (
    discover_topics,
    embed_texts,
    kmeans,
    name_topics,
    tfidf_embed,
)
from app_review_insights.llm import MockLLM


class KMeansTest(unittest.TestCase):
    def test_separates_two_blobs(self):
        points = [
            [0.0, 0.0], [0.1, 0.1], [0.2, 0.0],
            [10.0, 10.0], [10.1, 9.9], [9.9, 10.0],
        ]
        labels, _ = kmeans(points, k=2, seed=7)
        first = set(labels[:3])
        second = set(labels[3:])
        self.assertEqual(len(first | second), 2)


class EmbedTest(unittest.TestCase):
    def test_tfidf_vectors(self):
        vectors = tfidf_embed(["I love the workouts", "Too many ads", "App crashes every day"])
        self.assertEqual(len(vectors), 3)
        self.assertTrue(all(len(v) > 0 for v in vectors))

    def test_embed_texts_tfidf_backend(self):
        vectors, backend = embed_texts(["hello world", "world hello"], backend="tfidf")
        self.assertEqual(backend, "tfidf")
        self.assertEqual(len(vectors[0]), len(vectors[1]))


class NameTopicsTest(unittest.TestCase):
    def test_mock_naming(self):
        clusters = [
            {"topic_id": 0, "count": 2, "samples": [{"review_id": "a", "text": "ads"}]},
            {"topic_id": 1, "count": 1, "samples": [{"review_id": "b", "text": "crash"}]},
        ]
        llm = MockLLM(lambda m: {"topics": [
            {"topic_id": 0, "label": "广告打扰", "description": "d", "keywords": ["ads"]},
            {"topic_id": 1, "label": "崩溃问题", "description": "d", "keywords": ["crash"]},
        ]})
        named = name_topics(clusters, llm=llm)
        self.assertEqual(named[0]["label"], "广告打扰")
        self.assertEqual(named[1]["label"], "崩溃问题")

    def test_fallback_labels(self):
        clusters = [{"topic_id": 3, "count": 1, "samples": []}]
        named = name_topics(clusters, llm=None)
        self.assertEqual(named[0]["label"], "主题3")


class DiscoverTest(unittest.TestCase):
    def test_offline_discovery(self):
        reviews = [
            {"review_key": f"r{i}", "text": t, "title": "", "body": t, "helpful_votes": 0}
            for i, t in enumerate([
                "ads popup subscription every minute",
                "annoying popup paywall ads",
                "subscription prompt keeps appearing",
                "app crashes every time I open it",
                "crash on startup, cannot use",
                "crashes constantly and loses progress",
            ])
        ]
        result = discover_topics(reviews, embed_backend="tfidf")
        self.assertEqual(result["embed_backend"], "tfidf")
        self.assertEqual(len(result["memberships"]), 6)
        self.assertGreaterEqual(len(result["topics"]), 1)
        self.assertFalse(result["model_driven"])


if __name__ == "__main__":
    unittest.main()
