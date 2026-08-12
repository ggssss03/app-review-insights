import json
import pathlib
import tempfile
import unittest

from app_review_insights.loader import load_raw_reviews
from app_review_insights.models import utcnow_iso
from app_review_insights.storage import envelope


class LoadRawReviewsTest(unittest.TestCase):
    def _write(self, tmp: pathlib.Path, name: str, payload: dict) -> pathlib.Path:
        path = tmp / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_loads_itml_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            self._write(tmp, "reviews-itml-mostRecent-p0.json", envelope(
                "839285684", "https://itunes.apple.com/WebObjects/MZStore.woa/wa/userReviewsRow",
                {"userReviewList": [
                    {"userReviewId": "u1", "body": "Nice", "date": "2024-01-01T00:00:00Z",
                     "name": "Alice", "rating": 5, "title": "Great", "voteSum": 3},
                    {"userReviewId": "u2", "body": "Ads too many", "date": "2024-01-02T00:00:00Z",
                     "name": "Bob", "rating": 2, "title": "Meh", "voteSum": 0},
                ]},
                utcnow_iso(),
            ))
            reviews = load_raw_reviews(tmp, "839285684")
        self.assertEqual(len(reviews), 2)
        self.assertEqual(reviews[0].source, "itml")
        self.assertEqual(reviews[0].review_id, "u1")
        self.assertEqual(reviews[0].rating, 5)
        self.assertEqual(reviews[1].body, "Ads too many")
        self.assertEqual(reviews[1].helpful_votes, 0)

    def test_loads_amp_page_shelf(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            self._write(tmp, "reviews-amp-page-cn.json", envelope(
                "839285684", "https://apps.apple.com/cn/app/id839285684",
                {"shelfMapping": {"allProductReviews": {"items": [
                    {"review": {"id": "c1", "title": "好用", "contents": "每天练",
                                "date": "2018-02-15T14:20:16.000Z", "rating": 5,
                                "reviewerName": "小鸭"}},
                    {"review": {"id": "c2", "title": "Convenient", "contents": "I like it",
                                "date": "2018-12-04T16:29:19.000Z", "rating": 4,
                                "reviewerName": "Yayulia"}},
                ]}}},
                utcnow_iso(),
            ))
            reviews = load_raw_reviews(tmp, "839285684")
        self.assertEqual(len(reviews), 2)
        self.assertEqual(reviews[0].source, "amp-page")
        self.assertEqual(reviews[0].review_id, "c1")
        self.assertEqual(reviews[0].author, "小鸭")
        self.assertEqual(reviews[1].rating, 4)

    def test_skips_app_and_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            self._write(tmp, "app.json", {"app_id": "1"})
            self._write(tmp, "collection_notes.json", {"app_id": "1"})
            reviews = load_raw_reviews(tmp, "1")
        self.assertEqual(reviews, [])


if __name__ == "__main__":
    unittest.main()
