import base64
import importlib.util
from pathlib import Path
import tempfile
import unittest

from shared.storage import StatsRepository


class FakeSearchIndex:
    def __init__(self):
        self.documents = []

    def upsert_documents(self, documents):
        self.documents.extend(documents)

    def search(self, query, limit=100000, attributes=None):
        return {"hits": []}


def load_review_module():
    path = Path(__file__).resolve().parents[1] / "private-review" / "app.py"
    spec = importlib.util.spec_from_file_location("stats_review_app", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReviewAppTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.repository = StatsRepository(
            database_path=str(root / "stats.sqlite3"),
            image_dir=str(root / "images"),
        )
        self.repository.initialize()
        self.search = FakeSearchIndex()
        review_module = load_review_module()
        self.app = review_module.create_review_app(
            repository=self.repository, search_index=self.search
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_review_approval_updates_database_and_search(self):
        image = "data:image/png;base64," + base64.b64encode(b"image").decode()
        submission_id = self.repository.create_submission(
            image,
            {
                "Name": "Example",
                "Date": "2026-07-26",
                "Grade distribution": {"1.0": "1"},
            },
        )
        approved = {
            "Name": "Example",
            "Module Number": "IN0001",
            "Date": "2026-07-26",
            "Grade distribution": {"1.0": "1"},
        }

        with self.app.test_client() as client:
            index_response = client.get("/")
            image_response = client.get("/submission-image/" + submission_id)
            response = client.post(
                "/update/" + submission_id, json={"data": approved}
            )

        self.assertEqual(index_response.status_code, 200)
        self.assertEqual(image_response.data, b"image")
        image_response.close()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        self.assertEqual(self.search.documents[0]["id"], "IN0001_2026-07-26")
        self.assertEqual(self.repository.pending_outbox(), [])


if __name__ == "__main__":
    unittest.main()
