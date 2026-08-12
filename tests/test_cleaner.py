import unittest

from app_review_insights.cleaner import clean_reviews, detect_lang, is_junk, scrub_pii
from app_review_insights.models import ReviewRaw


def review(**kwargs) -> ReviewRaw:
    defaults = dict(
        source="import", app_id="839285684", review_id="", author="u",
        rating=5, title="", body="", version="", country="us",
        updated="", helpful_votes=0, page_url="", sort_by="",
    )
    defaults.update(kwargs)
    return ReviewRaw.create(**defaults)


class DedupTest(unittest.TestCase):
    def test_dedup_by_review_id(self):
        raw = [review(review_id="r1", body="one"), review(review_id="r1", body="one"), review(review_id="r2", body="two")]
        result = clean_reviews(raw)
        self.assertEqual(result["stats"]["unique_count"], 2)
        self.assertEqual(result["stats"]["removed_duplicates"], 1)

    def test_dedup_by_content_hash_without_id(self):
        raw = [
            review(author="A", updated="2026-01-01", title="T", body="same text"),
            review(author="A", updated="2026-01-01", title="T", body="same text"),
        ]
        result = clean_reviews(raw)
        self.assertEqual(result["stats"]["unique_count"], 1)

    def test_dedup_same_content_different_ids(self):
        raw = [
            review(review_id="r1", author="A", updated="2026-01-01", title="T", body="same text"),
            review(review_id="r2", author="A", updated="2026-01-01", title="T", body="same text"),
        ]
        result = clean_reviews(raw)
        self.assertEqual(result["stats"]["unique_count"], 1)
        self.assertEqual(result["stats"]["removed_duplicates"], 1)


class JunkTest(unittest.TestCase):
    def test_too_short(self):
        self.assertTrue(is_junk(review(body="a"))[0])

    def test_symbols_only(self):
        self.assertTrue(is_junk(review(body="!!!!  😂😂😂"))[0])

    def test_normal_not_junk(self):
        self.assertFalse(is_junk(review(body="Very useful workout app, I use it daily."))[0])


class PiiTest(unittest.TestCase):
    def test_email_masked(self):
        self.assertNotIn("foo@bar.com", scrub_pii("contact foo@bar.com please"))
        self.assertIn("[EMAIL]", scrub_pii("contact foo@bar.com please"))

    def test_phone_masked(self):
        self.assertIn("[PHONE]", scrub_pii("call me 138-0013-8000"))


class LangTest(unittest.TestCase):
    def test_zh(self):
        self.assertEqual(detect_lang("这个应用很好用，推荐！"), "zh")

    def test_en(self):
        self.assertEqual(detect_lang("Great app, love the workouts"), "en")

    def test_unknown_empty(self):
        self.assertEqual(detect_lang(""), "unknown")


if __name__ == "__main__":
    unittest.main()
