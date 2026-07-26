import argparse
import datetime
import json
import sqlite3
from pathlib import Path

from shared.search_index import SearchIndex, reconcile_outbox
from shared.storage import StatsRepository


def backup_database(repository, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = repository.connect()
    target = sqlite3.connect(str(destination))
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return destination


def export_exams(repository, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as file:
        json.dump(repository.all_exams(), file, ensure_ascii=False, indent=2)
    return destination


def rebuild_search(repository, search_index):
    search_index.wait_until_ready()
    search_index.delete_index()
    search_index.ensure_index()
    exams = repository.all_exams()
    for offset in range(0, len(exams), 500):
        search_index.upsert_documents(exams[offset : offset + 500])
    return len(exams)


def main():
    parser = argparse.ArgumentParser(description="TUM Stats administration")
    subcommands = parser.add_subparsers(dest="command", required=True)
    backup = subcommands.add_parser("backup")
    backup.add_argument(
        "destination",
        nargs="?",
        default="/runtime/backups/stats-{}.sqlite3".format(
            datetime.date.today().isoformat()
        ),
    )
    export = subcommands.add_parser("export-exams")
    export.add_argument("destination", nargs="?", default="/runtime/exams.json")
    subcommands.add_parser("reconcile-search")
    subcommands.add_parser("rebuild-search")
    args = parser.parse_args()

    repository = StatsRepository()
    repository.initialize()
    if args.command == "backup":
        print(str(backup_database(repository, args.destination)))
    elif args.command == "export-exams":
        print(str(export_exams(repository, args.destination)))
    elif args.command == "reconcile-search":
        search_index = SearchIndex()
        search_index.wait_until_ready()
        search_index.ensure_index()
        print(json.dumps(reconcile_outbox(repository, search_index)))
    elif args.command == "rebuild-search":
        print(json.dumps({"indexed": rebuild_search(repository, SearchIndex())}))


if __name__ == "__main__":
    main()
