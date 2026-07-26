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
    def search(self, query, limit=100000, attributes=None):
        return {"hits": [{"Name": "Example", "Grade distribution": {"1.0": "1"}}]}


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


if __name__ == "__main__":
    unittest.main()
