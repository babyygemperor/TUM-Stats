# TUM Exam Statistics

All the stats in here are updated to https://stats.aamin.dev

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
