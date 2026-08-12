import json
import pathlib
import tempfile
import unittest

from app_review_insights.collector import (
    build_rss_url,
    extract_app_id,
    extract_amp_token,
    parse_amp_payload,
    parse_review_entry,
    parse_review_feed,
)


def sample_entry() -> dict:
    return {
        "id": {"label": "https://itunes.apple.com/us/review?id=839285684&type=Purple%20Software"},
        "author": {"name": {"label": "Alice"}},
        "im:rating": {"label": "5"},
        "title": {"label": "Love it"},
        "content": {"label": "Great workout app, easy to follow!"},
        "im:version": {"label": "9.4.0"},
        "updated": {"label": "2026-08-01T12:00:00-07:00"},
        "im:voteSum": {"label": "3"},
    }


class ExtractAppIdTest(unittest.TestCase):
    def test_raw_id(self):
        self.assertEqual(extract_app_id("839285684"), "839285684")

    def test_app_store_url(self):
        url = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"
        self.assertEqual(extract_app_id(url), "839285684")

    def test_cn_app_store_url(self):
        url = "https://apps.apple.com/cn/app/workout-for-women-home-gym/id839285684"
        self.assertEqual(extract_app_id(url), "839285684")

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            extract_app_id("not-a-link")


class ParseReviewTest(unittest.TestCase):
    def test_parse_entry_fields(self):
        review = parse_review_entry(
            sample_entry(), source="rss", app_id="839285684", country="us",
            page_url="http://example/rss", sort_by="mostRecent", fetched_at="2026-08-12T00:00:00+00:00",
        )
        self.assertIsNotNone(review)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.author, "Alice")
        self.assertEqual(review.body, "Great workout app, easy to follow!")
        self.assertEqual(review.version, "9.4.0")
        self.assertEqual(review.helpful_votes, 3)
        self.assertEqual(review.sort_by, "mostRecent")

    def test_parse_feed_list_and_single(self):
        feed_list = {"feed": {"entry": [sample_entry(), sample_entry()]}}
        reviews = parse_review_feed(
            feed_list, source="rss", app_id="839285684", country="us",
            page_url="u", sort_by="s", fetched_at="t",
        )
        self.assertEqual(len(reviews), 2)

        feed_single = {"feed": {"entry": sample_entry()}}
        reviews = parse_review_feed(
            feed_single, source="rss", app_id="839285684", country="us",
            page_url="u", sort_by="s", fetched_at="t",
        )
        self.assertEqual(len(reviews), 1)

    def test_parse_feed_empty(self):
        reviews = parse_review_feed(
            {"feed": {}}, source="rss", app_id="1", country="us",
            page_url="u", sort_by="s", fetched_at="t",
        )
        self.assertEqual(reviews, [])

    def test_build_rss_url(self):
        url = build_rss_url("839285684", "mostRecent", 2)
        self.assertIn("/us/rss/customerreviews/id=839285684/page=2/sortBy=mostRecent/json", url)


class AmpParseTest(unittest.TestCase):
    def test_extract_token(self):
        html = '<script>{"token":"abc123.def456","other":1}</script>'
        self.assertEqual(extract_amp_token(html), "abc123.def456")

    def test_extract_token_near_amp_api(self):
        html = 'x' * 100 + 'amp-api.apps.apple.com/v1/catalog"token":"tok-xyz"'
        self.assertEqual(extract_amp_token(html), "tok-xyz")

    def test_missing_token_raises(self):
        with self.assertRaises(ValueError):
            extract_amp_token("<html>no token here</html>")

    def test_parse_amp_payload(self):
        payload = {"data": [
            {"id": "a1", "attributes": {
                "rating": 5, "title": "Great", "review": "Love it",
                "date": "2026-08-01T00:00:00Z", "version": "8.5.0", "author": "Alice",
            }},
            {"id": "a2", "attributes": {"rating": 1, "review": "Bad", "date": "2026-08-02T00:00:00Z"}},
        ]}
        reviews = parse_amp_payload(
            payload, source="amp", app_id="839285684", country="us",
            page_url="u", sort_by="relevance", fetched_at="t",
        )
        self.assertEqual(len(reviews), 2)
        self.assertEqual(reviews[0].review_id, "a1")
        self.assertEqual(reviews[0].rating, 5)
        self.assertEqual(reviews[0].body, "Love it")
        self.assertEqual(reviews[1].rating, 1)


if __name__ == "__main__":
    unittest.main()
