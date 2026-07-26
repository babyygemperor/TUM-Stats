import base64
import datetime
import hashlib
import json
import mimetypes
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path


DEFAULT_DATABASE_PATH = "runtime/stats.sqlite3"
DEFAULT_IMAGE_DIR = "runtime/images"


def utcnow():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def canonical_json(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(data):
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


class StatsRepository:
    def __init__(self, database_path=None, image_dir=None):
        self.database_path = database_path or os.environ.get(
            "STATS_DATABASE_PATH", DEFAULT_DATABASE_PATH
        )
        self.image_dir = Path(
            image_dir or os.environ.get("STATS_IMAGE_DIR", DEFAULT_IMAGE_DIR)
        )

    def connect(self):
        database_parent = Path(self.database_path).parent
        database_parent.mkdir(parents=True, exist_ok=True)
        self.image_dir.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextmanager
    def transaction(self):
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self):
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS submissions (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK (
                        status IN (
                            'uploaded', 'pending_review', 'approved',
                            'rejected', 'failed'
                        )
                    ),
                    image_path TEXT,
                    extracted_data TEXT NOT NULL,
                    reviewed_data TEXT,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    processing_error TEXT
                );

                CREATE INDEX IF NOT EXISTS submissions_status_created_idx
                    ON submissions(status, created_at);
                CREATE INDEX IF NOT EXISTS submissions_hash_idx
                    ON submissions(content_hash);
                CREATE UNIQUE INDEX IF NOT EXISTS submissions_active_hash_unique
                    ON submissions(content_hash)
                    WHERE status IN ('pending_review', 'approved');

                CREATE TABLE IF NOT EXISTS exams (
                    id TEXT PRIMARY KEY,
                    module_number TEXT NOT NULL,
                    exam_date TEXT NOT NULL,
                    name TEXT NOT NULL,
                    data TEXT NOT NULL,
                    source_submission_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(source_submission_id) REFERENCES submissions(id)
                );

                CREATE INDEX IF NOT EXISTS exams_module_date_idx
                    ON exams(module_number, exam_date);

                CREATE TABLE IF NOT EXISTS search_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation TEXT NOT NULL CHECK(operation IN ('upsert', 'delete')),
                    exam_id TEXT NOT NULL,
                    payload TEXT,
                    status TEXT NOT NULL DEFAULT 'pending' CHECK(
                        status IN ('pending', 'completed', 'failed')
                    ),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );

                CREATE INDEX IF NOT EXISTS search_outbox_status_idx
                    ON search_outbox(status, id);

                CREATE TABLE IF NOT EXISTS legacy_imports (
                    source TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    records_imported INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notification_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def _store_data_url(self, data_url, submission_id):
        if not data_url:
            return None
        try:
            header, encoded = data_url.split(",", 1)
            media_type = header.split(";", 1)[0].split(":", 1)[1]
            image_bytes = base64.b64decode(encoded, validate=True)
        except (ValueError, IndexError):
            raise ValueError("Invalid image data URL")

        extension = mimetypes.guess_extension(media_type) or ".img"
        if extension == ".jpe":
            extension = ".jpg"
        relative_path = Path(
            datetime.datetime.utcnow().strftime("%Y/%m")
        ) / (submission_id + extension)
        destination = self.image_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(image_bytes)
        os.replace(str(temporary), str(destination))
        return str(relative_path)

    def create_submission(self, image_data, data, submission_id=None, created_at=None):
        submission_id = submission_id or str(uuid.uuid4())
        created_at = created_at or utcnow()
        digest = content_hash(data)

        with self.connect() as connection:
            duplicate = connection.execute(
                """
                SELECT id FROM submissions
                WHERE content_hash = ? AND status IN ('pending_review', 'approved')
                LIMIT 1
                """,
                (digest,),
            ).fetchone()
        if duplicate:
            return None

        image_path = self._store_data_url(image_data, submission_id)
        try:
            with self.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO submissions (
                        id, status, image_path, extracted_data, content_hash, created_at
                    ) VALUES (?, 'pending_review', ?, ?, ?, ?)
                    """,
                    (
                        submission_id,
                        image_path,
                        canonical_json(data),
                        digest,
                        created_at,
                    ),
                )
        except sqlite3.IntegrityError:
            if image_path:
                try:
                    (self.image_dir / image_path).unlink()
                except FileNotFoundError:
                    pass
            return None
        except Exception:
            if image_path:
                try:
                    (self.image_dir / image_path).unlink()
                except FileNotFoundError:
                    pass
            raise
        return submission_id

    def list_pending_submissions(self):
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM submissions
                WHERE status = 'pending_review'
                ORDER BY created_at
                """
            ).fetchall()
        return [self._submission_from_row(row) for row in rows]

    def pending_summary(self):
        pending = self.list_pending_submissions()
        return len(pending), pending

    def get_submission(self, submission_id):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM submissions WHERE id = ?", (submission_id,)
            ).fetchone()
        return self._submission_from_row(row) if row else None

    def _submission_from_row(self, row):
        return {
            "id": row["id"],
            "status": row["status"],
            "image_path": row["image_path"],
            "data": json.loads(row["reviewed_data"] or row["extracted_data"]),
            "timestamp": row["created_at"],
            "processed": row["status"] == "approved",
        }

    def approve_submission(self, submission_id, data):
        module_number = str(data.get("Module Number", "")).strip()
        exam_date = str(data.get("Date", "")).strip()
        name = str(data.get("Name", "")).strip()
        if not module_number:
            raise ValueError("Module Number is invalid")
        if not exam_date:
            raise ValueError("Date is invalid")

        exam_id = module_number + "_" + exam_date
        approved_data = dict(data)
        approved_data["Module Number"] = module_number
        approved_data["Date"] = exam_date
        approved_data["id"] = exam_id
        now = utcnow()
        payload = canonical_json(approved_data)

        with self.transaction() as connection:
            submission = connection.execute(
                "SELECT id FROM submissions WHERE id = ?", (submission_id,)
            ).fetchone()
            if not submission:
                raise KeyError(submission_id)
            connection.execute(
                """
                UPDATE submissions
                SET status = 'approved', reviewed_data = ?, reviewed_at = ?
                WHERE id = ?
                """,
                (payload, now, submission_id),
            )
            connection.execute(
                """
                INSERT INTO exams (
                    id, module_number, exam_date, name, data,
                    source_submission_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    module_number = excluded.module_number,
                    exam_date = excluded.exam_date,
                    name = excluded.name,
                    data = excluded.data,
                    source_submission_id = excluded.source_submission_id,
                    updated_at = excluded.updated_at
                """,
                (
                    exam_id,
                    module_number,
                    exam_date,
                    name,
                    payload,
                    submission_id,
                    now,
                    now,
                ),
            )
            cursor = connection.execute(
                """
                INSERT INTO search_outbox (
                    operation, exam_id, payload, status, created_at
                ) VALUES ('upsert', ?, ?, 'pending', ?)
                """,
                (exam_id, payload, now),
            )
        return approved_data, cursor.lastrowid

    def mark_legacy_submission_approved(self, submission_id, data):
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE submissions
                SET status = 'approved', reviewed_data = ?, reviewed_at = ?
                WHERE id = ?
                """,
                (canonical_json(data), utcnow(), submission_id),
            )

    def all_exams(self):
        with self.connect() as connection:
            rows = connection.execute("SELECT data FROM exams ORDER BY id").fetchall()
        return [json.loads(row["data"]) for row in rows]

    def pending_outbox(self):
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM search_outbox
                WHERE status IN ('pending', 'failed')
                ORDER BY id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def complete_outbox(self, outbox_id):
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE search_outbox
                SET status = 'completed', attempts = attempts + 1,
                    last_error = NULL, completed_at = ?
                WHERE id = ?
                """,
                (utcnow(), outbox_id),
            )

    def fail_outbox(self, outbox_id, error):
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE search_outbox
                SET status = 'failed', attempts = attempts + 1, last_error = ?
                WHERE id = ?
                """,
                (str(error)[:1000], outbox_id),
            )

    def import_exam(self, data):
        module_number = str(data.get("Module Number", "")).strip()
        exam_date = str(data.get("Date", "")).strip()
        exam_id = str(data.get("id") or (module_number + "_" + exam_date))
        if not exam_id or exam_id == "_":
            exam_id = hashlib.sha256(canonical_json(data).encode()).hexdigest()
        stored_data = dict(data)
        stored_data["id"] = exam_id
        now = utcnow()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO exams (
                    id, module_number, exam_date, name, data, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    module_number = excluded.module_number,
                    exam_date = excluded.exam_date,
                    name = excluded.name,
                    data = excluded.data,
                    updated_at = excluded.updated_at
                """,
                (
                    exam_id,
                    module_number,
                    exam_date,
                    str(data.get("Name", "")),
                    canonical_json(stored_data),
                    now,
                    now,
                ),
            )

    def legacy_import_current(self, source, fingerprint):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT fingerprint FROM legacy_imports WHERE source = ?", (source,)
            ).fetchone()
        return bool(row and row["fingerprint"] == fingerprint)

    def record_legacy_import(self, source, fingerprint, count):
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO legacy_imports (
                    source, fingerprint, imported_at, records_imported
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    fingerprint = excluded.fingerprint,
                    imported_at = excluded.imported_at,
                    records_imported = excluded.records_imported
                """,
                (source, fingerprint, utcnow(), count),
            )
