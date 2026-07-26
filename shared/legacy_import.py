import hashlib
import json
from pathlib import Path

from shared.storage import StatsRepository, canonical_json


def file_fingerprint(path):
    stat = path.stat()
    return "{}:{}".format(stat.st_size, stat.st_mtime_ns)


def import_exam_file(repository, path):
    path = Path(path)
    if not path.exists():
        return 0
    fingerprint = file_fingerprint(path)
    source = str(path.resolve())
    if repository.legacy_import_current(source, fingerprint):
        return 0
    with path.open(encoding="utf-8") as file:
        records = json.load(file)
    for record in records:
        repository.import_exam(record)
    repository.record_legacy_import(source, fingerprint, len(records))
    return len(records)


def import_submission_file(repository, path):
    path = Path(path)
    if not path.exists():
        return 0
    fingerprint = file_fingerprint(path)
    source = str(path.resolve())
    if repository.legacy_import_current(source, fingerprint):
        return 0

    with path.open(encoding="utf-8") as file:
        records = json.load(file)

    imported = 0
    for record in records:
        data = record.get("data")
        if not isinstance(data, dict):
            continue
        timestamp = str(record.get("timestamp") or "")
        submission_id = timestamp or hashlib.sha256(
            canonical_json(record).encode("utf-8")
        ).hexdigest()
        existing = repository.get_submission(submission_id)
        if existing:
            continue
        created = repository.create_submission(
            record.get("image"),
            data,
            submission_id=submission_id,
            created_at=timestamp or None,
        )
        if created:
            imported += 1
            if record.get("processed"):
                repository.mark_legacy_submission_approved(submission_id, data)

    repository.record_legacy_import(source, fingerprint, imported)
    return imported


def import_legacy_data(repository=None, stats_dir="/legacy-stats"):
    repository = repository or StatsRepository()
    repository.initialize()
    stats_dir = Path(stats_dir)
    result = {
        "master": import_exam_file(repository, stats_dir / "master_with_id.json"),
        "approved": import_exam_file(repository, stats_dir / "new_data_only.json"),
        "submissions": import_submission_file(
            repository, stats_dir / "new_data.json"
        ),
    }
    return result
