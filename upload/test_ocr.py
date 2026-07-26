import json
import os
import unittest
from unittest.mock import Mock, patch

from ocr import (
    DEFAULT_MODEL,
    OCRServiceError,
    _normalize_legacy_contract,
    extract_from_image,
)


class ExtractFromImageTests(unittest.TestCase):
    def setUp(self):
        self.api_key = patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True)
        self.api_key.start()

    def tearDown(self):
        self.api_key.stop()

    @patch("ocr.requests.post")
    def test_returns_parsed_statistics(self, post):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {
            "choices": [{"message": {"content": json.dumps({"Name": "Statistics"})}}]
        }
        post.return_value = response

        result = extract_from_image("encoded-image")

        self.assertEqual(result, {"Name": "Statistics"})
        request_payload = post.call_args.kwargs["json"]
        self.assertEqual(request_payload["model"], DEFAULT_MODEL)
        self.assertNotIn("response_format", request_payload)
        self.assertEqual(post.call_args.kwargs["timeout"], 60)
        prompt = request_payload["messages"][0]["content"][0]["text"]
        self.assertIn('"Grade distribution" : {', prompt)
        self.assertIn('"1.0": "0"', prompt)
        self.assertIn('"5.0X": "36"', prompt)

    @patch("ocr.requests.post")
    def test_uses_configured_model(self, post):
        os.environ["OPENAI_OCR_MODEL"] = "custom-model"
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {
            "choices": [{"message": {"content": '{"Name": "Statistics"}'}}]
        }
        post.return_value = response

        extract_from_image("encoded-image")

        self.assertEqual(post.call_args.kwargs["json"]["model"], "custom-model")

    @patch("ocr.requests.post")
    def test_reports_openai_error_instead_of_raising_key_error(self, post):
        response = Mock(ok=False, status_code=429)
        response.json.return_value = {
            "error": {"message": "Rate limit reached", "type": "rate_limit_error"}
        }
        post.return_value = response

        with self.assertRaisesRegex(OCRServiceError, "Rate limit reached"):
            extract_from_image("encoded-image")

    @patch("ocr.requests.post")
    def test_rejects_success_response_without_choices(self, post):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"id": "response-without-choices"}
        post.return_value = response

        with self.assertRaisesRegex(OCRServiceError, "unexpected response"):
            extract_from_image("encoded-image")

    @patch("ocr.requests.post")
    def test_preserves_legacy_unrelated_image_message(self, post):
        message = (
            "The provided image does not contain relevant textual information about "
            "an academic course or exam results to convert into JSON format."
        )
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {
            "choices": [{"message": {"content": message}}]
        }
        post.return_value = response

        self.assertEqual(extract_from_image("encoded-image"), message)

    def test_normalizes_grade_rows_to_legacy_grade_object(self):
        result = _normalize_legacy_contract(
            {
                "Name": "Statistics",
                "Date": None,
                "Registered": 437,
                "Grade distribution": [
                    {"Grade": "1.0 sehr gut", "Count": 40},
                    {
                        "Grade": "X",
                        "Description": "Nicht erschienen",
                        "Count": 104,
                    },
                ],
            }
        )

        self.assertEqual(result["Registered"], "437")
        self.assertEqual(result["Date"], "")
        self.assertEqual(
            result["Grade distribution"],
            {"1.0": "40", "5.0X": "104"},
        )

    def test_normalizes_dictionary_grades_and_missing_name(self):
        result = _normalize_legacy_contract(
            {
                "Grade distribution": {"1,0": 3, "X": 18},
                "Grade percentages": {"1.0": "14.29%"},
            }
        )

        self.assertEqual(result["Name"], "")
        self.assertNotIn("Grade percentages", result)
        self.assertEqual(
            result["Grade distribution"],
            {"1.0": "3", "5.0X": "18"},
        )


if __name__ == "__main__":
    unittest.main()
