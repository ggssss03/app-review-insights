import json
import pathlib
import tempfile
import unittest
from unittest import mock

from app_review_insights.collector import (
    build_rss_url,
    extract_country,
    extract_app_id,
    extract_amp_token,
    fetch_itml_reviews,
    fetch_reviews,
    storefront_for,
    parse_amp_payload,
    parse_itml_payload,
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

    def test_extract_country(self):
        self.assertEqual(extract_country("https://apps.apple.com/cn/app/id839285684"), "cn")
        self.assertEqual(extract_country("https://apps.apple.com/us/app/id839285684"), "us")
        self.assertEqual(extract_country("839285684"), "cn")
        self.assertEqual(extract_country("https://apps.apple.com/jp/app/id839285684"), "cn")

    def test_storefront_for(self):
        self.assertEqual(storefront_for("cn"), "143465-1,29")
        self.assertEqual(storefront_for("us"), "143441-1,29")


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


class ItmlParseTest(unittest.TestCase):
    def test_parse_itml_payload(self):
        payload = {
            "userReviewList": [
                {
                    "userReviewId": "11593815773",
                    "body": "I love the layout and approach of this app.",
                    "date": "2024-08-10T13:23:49Z",
                    "name": "Kstu SLP mama",
                    "rating": 5,
                    "title": "Love it!",
                    "voteCount": 3,
                    "voteSum": 1,
                },
                {
                    "userReviewId": "5786142670",
                    "body": "No time? This is the app for you!",
                    "date": "2020-04-09T14:01:44Z",
                    "name": "Redhead4peace",
                    "rating": 4,
                    "title": "Great",
                    "voteCount": 25,
                    "voteSum": 20,
                },
            ]
        }
        reviews = parse_itml_payload(
            payload, source="itml", app_id="839285684", country="us",
            page_url="http://example/userReviewsRow", sort_by="mostRecent",
            fetched_at="2026-08-12T00:00:00+00:00",
        )
        self.assertEqual(len(reviews), 2)
        self.assertEqual(reviews[0].review_id, "11593815773")
        self.assertEqual(reviews[0].rating, 5)
        self.assertEqual(reviews[0].author, "Kstu SLP mama")
        self.assertEqual(reviews[0].body, "I love the layout and approach of this app.")
        self.assertEqual(reviews[0].helpful_votes, 1)
        self.assertEqual(reviews[1].rating, 4)
        self.assertEqual(reviews[1].helpful_votes, 20)

    def test_parse_itml_payload_empty_and_bad_rows(self):
        reviews = parse_itml_payload(
            {"userReviewList": []}, source="itml", app_id="1", country="us",
            page_url="u", sort_by="s", fetched_at="t",
        )
        self.assertEqual(reviews, [])
        reviews = parse_itml_payload(
            {"userReviewList": [None, {"userReviewId": "x", "rating": "5"}]},
            source="itml", app_id="1", country="us",
            page_url="u", sort_by="s", fetched_at="t",
        )
        self.assertEqual(len(reviews), 1)


class CountryAwareCollectTest(unittest.TestCase):
    def test_cn_fetch_uses_rss_and_parses_entries(self):
        payload = {"feed": {"entry": [
            {"id": {"label": "c1"}, "author": {"name": {"label": "甲"}},
             "im:rating": {"label": "1"}, "title": {"label": "都要开通会员"},
             "content": {"label": "所有项目都要开通会员，都要钱的"},
             "im:version": {"label": "8.5.0"}, "updated": {"label": "2026-01-01"},
             "im:voteSum": {"label": "2"}},
            {"id": {"label": "c2"}, "author": {"name": {"label": "乙"}},
             "im:rating": {"label": "5"}, "title": {"label": "非常好"},
             "content": {"label": "这个app非常好"},
             "im:version": {"label": "8.5.0"}, "updated": {"label": "2026-01-02"},
             "im:voteSum": {"label": "0"}},
        ]}}
        empty_feed = {"feed": {}}

        def fake_get(url, timeout=30):
            if "page=1" in url:
                return payload
            return empty_feed

        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = pathlib.Path(tmp) / "839285684"
            with mock.patch("app_review_insights.collector.http_get_json", side_effect=fake_get) as get:
                stats = fetch_reviews("839285684", country="cn", cache_dir=cache_dir, refresh=True)
        self.assertEqual(stats["reviews_total"], 4)
        self.assertEqual(stats["method"], "rss")
        self.assertEqual(stats["country"], "cn")
        url = get.call_args_list[0].args[0]
        self.assertIn("/cn/rss/customerreviews/id=839285684", url)

    def test_itml_rejects_cn(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                fetch_itml_reviews("839285684", country="cn", cache_dir=pathlib.Path(tmp))


if __name__ == "__main__":
    unittest.main()
