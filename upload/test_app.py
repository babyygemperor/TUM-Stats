import sys
import base64
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

flask_mail = types.ModuleType("flask_mail")
flask_mail.Mail = lambda app: object()
flask_mail.Message = object
sys.modules.setdefault("flask_mail", flask_mail)

from api.app import PROCESSING_ERROR_MESSAGE, app, create_public_app
from shared.storage import StatsRepository
from upload.ocr import OCRServiceError


class FakeSearchIndex:
    def __init__(self, hits=None):
        self.last_limit = None
        self.hits = hits or [
            {"Name": "Example", "Grade distribution": {"1.0": "1"}}
        ]

    def search(self, query, limit=100000, attributes=None):
        self.last_limit = limit
        return {"hits": self.hits}


class UploadErrorPrivacyTests(unittest.TestCase):
    @patch("api.app.extract_from_image")
    def test_provider_error_details_are_not_returned_to_user(self, extract):
        provider_details = (
            "OpenAI API rejected model gpt-5.6-luna: invalid_api_key"
        )
        extract.side_effect = OCRServiceError(provider_details)

        with app.test_client() as client:
            response = client.post(
                "/upload",
                data={"image": "data:image/jpeg;base64,encoded-image"},
            )

        response_text = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json(), {"error": PROCESSING_ERROR_MESSAGE})
        self.assertNotIn("OpenAI", response_text)
        self.assertNotIn("GPT", response_text.upper())
        self.assertNotIn("invalid_api_key", response_text)

    def test_submission_and_search_routes_share_the_public_app(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = StatsRepository(
                database_path=str(root / "stats.sqlite3"),
                image_dir=str(root / "images"),
            )
            public_app = create_public_app(
                repository=repository, search_index=FakeSearchIndex()
            )
            image = "data:image/png;base64," + base64.b64encode(b"image").decode()
            with public_app.test_client() as client:
                submission = client.post(
                    "/send",
                    json={
                        "image": image,
                        "data": {
                            "Name": "Example",
                            "Grade distribution": {"1.0": "1"},
                        },
                    },
                )
                search = client.post(
                    "/search", json={"query": "Example", "limit": 10}
                )

            self.assertEqual(submission.status_code, 200)
            self.assertIn("submission_id", submission.get_json())
            self.assertEqual(search.status_code, 200)
            self.assertEqual(search.get_json()["hits"][0]["Name"], "Example")

    def test_interactive_search_limits_full_chart_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = StatsRepository(
                database_path=str(root / "stats.sqlite3"),
                image_dir=str(root / "images"),
            )
            search_index = FakeSearchIndex()
            public_app = create_public_app(
                repository=repository, search_index=search_index
            )

            with public_app.test_client() as client:
                response = client.get("/search?query=IN")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(search_index.last_limit, 20)

    def test_suggestions_are_grouped_by_module_number(self):
        hits = [
            {
                "Module Number": "EI4693",
                "Name": "Introduction to Signal Processing for IN",
                "Date": "2025-02-01",
            },
            {
                "Module Number": "IN0001",
                "Name": "Old name",
                "Date": "2023-01-01",
            },
            {
                "Module Number": "IN0001",
                "Name": "Current name",
                "Date": "2025-01-01",
            },
            {
                "Module Number": "IN0002",
                "Name": "Another module",
                "Date": "2024-01-01",
            },
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = StatsRepository(
                database_path=str(root / "stats.sqlite3"),
                image_dir=str(root / "images"),
            )
            public_app = create_public_app(
                repository=repository, search_index=FakeSearchIndex(hits)
            )

            with public_app.test_client() as client:
                response = client.get("/suggest?query=IN")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.get_json(),
                [
                    {
                        "module_number": "IN0001",
                        "name": "Current name",
                        "latest_date": "2025-01-01",
                        "exam_count": 2,
                    },
                    {
                        "module_number": "IN0002",
                        "name": "Another module",
                        "latest_date": "2024-01-01",
                        "exam_count": 1,
                    },
                    {
                        "module_number": "EI4693",
                        "name": "Introduction to Signal Processing for IN",
                        "latest_date": "2025-02-01",
                        "exam_count": 1,
                    },
                ],
            )

    def test_selected_module_is_exact_and_sorted_newest_first(self):
        hits = [
            {
                "Module Number": "IN0001",
                "Name": "Older exam",
                "Date": "2023-01-01",
                "Grade distribution": {"1.0": "1"},
            },
            {
                "Module Number": "IN00010",
                "Name": "Different module",
                "Date": "2026-01-01",
                "Grade distribution": {"1.0": "1"},
            },
            {
                "Module Number": "IN0001",
                "Name": "Newer exam",
                "Date": "2025-01-01",
                "Grade distribution": {"1.0": "1"},
            },
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = StatsRepository(
                database_path=str(root / "stats.sqlite3"),
                image_dir=str(root / "images"),
            )
            public_app = create_public_app(
                repository=repository, search_index=FakeSearchIndex(hits)
            )

            with public_app.test_client() as client:
                response = client.get("/search/module?module=IN0001")

            rendered = response.get_json()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(rendered), 2)
            self.assertIn("Newer exam", rendered[0])
            self.assertIn("Older exam", rendered[1])
            self.assertNotIn("Different module", "".join(rendered))


if __name__ == "__main__":
    unittest.main()
