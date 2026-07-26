import base64
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = PROJECT_ROOT / "upload" / "examples"
REFERENCE_DATA = PROJECT_ROOT / "private-review" / "new_data_only.json"
RUN_LIVE_TESTS = os.environ.get("RUN_OCR_INTEGRATION") == "1"


def _load_env_file():
    """Load the local API settings without adding a dotenv dependency."""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        raise AssertionError(f"Missing integration-test environment file: {env_file}")

    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in {"OPENAI_API_KEY", "OPENAI_OCR_MODEL"}:
            os.environ[key] = value.strip().strip("'\"")


@unittest.skipUnless(
    RUN_LIVE_TESTS,
    "Set RUN_OCR_INTEGRATION=1 to run paid OCR API integration tests.",
)
class OCRIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _load_env_file()
        if not os.environ.get("OPENAI_API_KEY"):
            raise AssertionError("OPENAI_API_KEY is missing from .env")

        with REFERENCE_DATA.open(encoding="utf-8") as file:
            reference_records = json.load(file)
        if not reference_records:
            raise AssertionError(f"No reference records found in {REFERENCE_DATA}")

        cls.reference_grade_keys = {
            grade
            for record in reference_records
            for grade in record.get("Grade distribution", {})
        }

    def _extract_sample(self, image_path):
        from ocr import extract_from_image

        encoded_image = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return image_path.name, extract_from_image(encoded_image)

    def _assert_saved_json_contract(self, sample_name, result):
        context = f"OCR output for {sample_name}"
        self.assertIsInstance(result, dict, context)
        self.assertNotIn("Course", result, context)
        self.assertIsInstance(result.get("Name"), str, context)

        distribution = result.get("Grade distribution")
        self.assertIsInstance(distribution, dict, context)
        self.assertTrue(distribution, context)

        for field, value in result.items():
            if field == "Grade distribution":
                continue
            self.assertIsInstance(
                value,
                str,
                f"{context}: top-level field {field!r} must be a string",
            )

        for grade, count in distribution.items():
            self.assertIsInstance(grade, str, context)
            self.assertIn(
                grade,
                self.reference_grade_keys,
                f"{context}: grade key {grade!r} is absent from saved reference data",
            )
            self.assertIsInstance(count, str, context)
            self.assertTrue(
                count.isdigit(),
                f"{context}: grade count for {grade!r} must be an integer string",
            )

        # This is the envelope persisted in private-review/data.json.
        saved_entry = {
            "image": f"example:{sample_name}",
            "data": result,
            "timestamp": "integration-test",
        }
        serialized_entry = json.loads(json.dumps(saved_entry))
        self.assertEqual(serialized_entry["data"], result)

    def test_all_example_images_match_saved_json_contract(self):
        samples = sorted(EXAMPLES_DIR.glob("*.png"))
        self.assertTrue(samples, f"No sample images found in {EXAMPLES_DIR}")

        with ThreadPoolExecutor(max_workers=min(4, len(samples))) as executor:
            results = list(executor.map(self._extract_sample, samples))

        for sample_name, result in results:
            with self.subTest(sample=sample_name):
                self._assert_saved_json_contract(sample_name, result)


if __name__ == "__main__":
    unittest.main()
