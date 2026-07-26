# TUM Exam Statistics

All the stats in here are updated to https://stats.aamin.dev

## Architecture

- `stats-api` exposes public search, OCR preview, and submission routes on port
  `6655`.
- `stats-review` exposes the separately protected review application on port
  `9981`.
- SQLite at `runtime/stats.sqlite3` is the source of truth.
- Original submission images are decoded into `runtime/images/`.
- Meilisearch remains the required fuzzy-search index and persists its data in
  `runtime/meilisearch/`.
- `meilisearch-bootstrap` imports legacy JSON once, initializes SQLite, and
  idempotently seeds Meilisearch from approved SQLite records.

The JSON files under `stats/` are legacy import sources. The running
application no longer modifies or copies them.

## Deploying the refactor

The first startup imports the existing legacy JSON automatically. Build and
start the new services with:

```sh
docker compose up -d --build --remove-orphans
```

The `--remove-orphans` option removes the former standalone `stats-upload`
container. Upload routes now live on `stats-api` at port `6655`; production
URLs remain unchanged. Update Nginx to route all
`stats-api.aamin.dev` paths, including `/upload` and `/send`, to port `6655`
before removing the former upload container.

Check migration and startup status:

```sh
docker compose ps
docker compose logs meilisearch-bootstrap
docker compose logs stats-api stats-review
```

The bootstrap log reports imported submission/exam counts and the number of
documents indexed.

## Backup and recovery

Create a consistent online SQLite backup:

```sh
docker compose run --rm stats-review \
  python -m shared.admin backup
```

Export approved exams as portable JSON:

```sh
docker compose run --rm stats-review \
  python -m shared.admin export-exams
```

Retry search updates that failed after an approval:

```sh
docker compose run --rm stats-review \
  python -m shared.admin reconcile-search
```

Delete and completely rebuild the Meilisearch index from SQLite:

```sh
docker compose run --rm stats-review \
  python -m shared.admin rebuild-search
```

To move the deployment, copy a SQLite backup and `runtime/images/`.
Meilisearch can be rebuilt and does not need to be copied.

## OCR tests

Run the local unit tests without making API requests:

```sh
python3 -m unittest discover -s upload -p 'test_*.py' -v
```

Run the paid live OCR integration test against every image in
`upload/examples/`, using `OPENAI_API_KEY` from the local `.env` file:

```sh
RUN_OCR_INTEGRATION=1 python3 -m unittest discover \
  -s upload -p 'test_ocr_integration.py' -v
```

The live test compares each generated result with the persisted JSON contract
represented by `private-review/new_data_only.json`. It is opt-in so ordinary
test runs and CI do not make paid external requests.
