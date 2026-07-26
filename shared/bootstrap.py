import json
import os

from shared.legacy_import import import_legacy_data
from shared.search_index import SearchIndex, reconcile_outbox
from shared.storage import StatsRepository


def main():
    repository = StatsRepository()
    imported = import_legacy_data(
        repository, os.environ.get("LEGACY_STATS_DIR", "/legacy-stats")
    )

    search_index = SearchIndex()
    search_index.wait_until_ready()
    search_index.ensure_index()
    exams = repository.all_exams()
    batch_size = 500
    for offset in range(0, len(exams), batch_size):
        search_index.upsert_documents(exams[offset : offset + batch_size])
    outbox = reconcile_outbox(repository, search_index)

    print(
        json.dumps(
            {
                "imported": imported,
                "indexed": len(exams),
                "outbox": outbox,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    if outbox["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
