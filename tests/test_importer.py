import csv
import io
import json
import pathlib
import tempfile
import unittest

from app_review_insights.importer import import_csv_file, import_json_file


class ImportJsonTest(unittest.TestCase):
    def test_array_with_flexible_fields(self):
        payload = [
            {"review_id": "r1", "author": "Bob", "rating": "4", "title": "Good",
             "content": "Works well", "version": "1.2", "updated": "2026-01-01"},
            {"id": "r2", "author": "Carol", "stars": 2, "text": "Too many ads",
             "appVersion": "1.3"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "reviews.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            reviews = import_json_file(path, app_id="839285684")
        self.assertEqual(len(reviews), 2)
        self.assertEqual(reviews[0].review_id, "r1")
        self.assertEqual(reviews[0].rating, 4)
        self.assertEqual(reviews[1].rating, 2)
        self.assertEqual(reviews[1].body, "Too many ads")
        self.assertEqual(reviews[1].version, "1.3")

    def test_rss_feed_structure(self):
        payload = {"feed": {"entry": [
            {"id": {"label": "x1"}, "author": {"name": {"label": "A"}},
             "im:rating": {"label": "5"}, "title": {"label": "T"}, "content": {"label": "B"}},
        ]}}
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "feed.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            reviews = import_json_file(path, app_id="839285684")
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].author, "A")
        self.assertEqual(reviews[0].rating, 5)


class ImportCsvTest(unittest.TestCase):
    def test_csv(self):
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["id", "author", "rating", "content", "date"])
        writer.writeheader()
        writer.writerow({"id": "c1", "author": "Dan", "rating": "3", "content": "OK app", "date": "2026-02-02"})
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "reviews.csv"
            path.write_text(buf.getvalue(), encoding="utf-8")
            reviews = import_csv_file(path, app_id="839285684")
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0].review_id, "c1")
        self.assertEqual(reviews[0].rating, 3)
        self.assertEqual(reviews[0].updated, "2026-02-02")


if __name__ == "__main__":
    unittest.main()
