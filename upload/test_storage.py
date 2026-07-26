import base64
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from shared.admin import backup_database, export_exams
from shared.legacy_import import import_exam_file
from shared.storage import StatsRepository


class StatsRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.repository = StatsRepository(
            database_path=str(root / "stats.sqlite3"),
            image_dir=str(root / "images"),
        )
        self.repository.initialize()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_submission_image_and_approval_are_persisted(self):
        image = "data:image/png;base64," + base64.b64encode(b"image").decode()
        data = {
            "Name": "Example",
            "Module Number": "IN0001",
            "Date": "2026-07-26",
            "Grade distribution": {"1.0": "1"},
        }

        submission_id = self.repository.create_submission(image, data)

        self.assertIsNotNone(submission_id)
        submission = self.repository.get_submission(submission_id)
        self.assertEqual(submission["status"], "pending_review")
        self.assertTrue(
            (self.repository.image_dir / submission["image_path"]).exists()
        )
        self.assertIsNone(self.repository.create_submission(image, data))

        approved, outbox_id = self.repository.approve_submission(
            submission_id, data
        )

        self.assertEqual(approved["id"], "IN0001_2026-07-26")
        self.assertEqual(
            self.repository.get_submission(submission_id)["status"], "approved"
        )
        self.assertEqual(self.repository.all_exams(), [approved])
        self.assertEqual(self.repository.pending_outbox()[0]["id"], outbox_id)

        self.repository.complete_outbox(outbox_id)
        self.assertEqual(self.repository.pending_outbox(), [])

    def test_legacy_exam_import_is_idempotent(self):
        legacy_file = Path(self.temporary_directory.name) / "legacy.json"
        legacy_file.write_text(
            json.dumps(
                [
                    {
                        "id": "IN0001_2026-07-26",
                        "Module Number": "IN0001",
                        "Date": "2026-07-26",
                        "Name": "Example",
                        "Grade distribution": {"1.0": "1"},
                    }
                ]
            ),
            encoding="utf-8",
        )

        self.assertEqual(import_exam_file(self.repository, legacy_file), 1)
        self.assertEqual(import_exam_file(self.repository, legacy_file), 0)
        self.assertEqual(len(self.repository.all_exams()), 1)

        backup = Path(self.temporary_directory.name) / "backup.sqlite3"
        export = Path(self.temporary_directory.name) / "exams.json"
        backup_database(self.repository, backup)
        export_exams(self.repository, export)
        with sqlite3.connect(str(backup)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM exams").fetchone()[0],
                1,
            )
        self.assertEqual(len(json.loads(export.read_text(encoding="utf-8"))), 1)


if __name__ == "__main__":
    unittest.main()
