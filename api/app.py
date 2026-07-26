import logging
import os

from flask import Flask, jsonify, request

from shared.rendering import json_to_html
from shared.search_index import SearchIndex, SearchIndexError
from shared.storage import StatsRepository
from upload.email_service import check_send_email, configure_mail, send_email
from upload.ocr import OCRServiceError, extract_from_image


PROCESSING_ERROR_MESSAGE = "Image processing failed. Please try again."
INTERACTIVE_SEARCH_LIMIT = 20
MODULE_SEARCH_LIMIT = 1000
SUGGESTION_SEARCH_LIMIT = 100
SUGGESTION_LIMIT = 8
SEARCH_ATTRIBUTES = [
    "Date",
    "Module Number",
    "Name",
    "Registered",
    "Attempt made",
    "Not present",
    "Withdrawal with approved reasons",
    "Not valid/cheating",
    "Rejection",
    "Average total",
    "Average (assessed as passed)",
    "Grade distribution",
]


def create_public_app(repository=None, search_index=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = int(
        os.environ.get("MAX_UPLOAD_BYTES", 15 * 1024 * 1024)
    )
    mail = configure_mail(app)
    repository = repository or StatsRepository()
    repository.initialize()
    search_index = search_index or SearchIndex()

    @app.after_request
    def add_headers(response):
        response.headers["Access-Control-Allow-Origin"] = os.environ.get(
            "CORS_ALLOW_ORIGIN", "*"
        )
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    @app.route("/health", methods=["GET"])
    def health():
        return {"status": "ok"}

    @app.route("/upload", methods=["POST"])
    def upload_file():
        image_data = request.form.get("image")
        if not image_data:
            return jsonify({"error": "No image data"}), 400

        try:
            _, base64_image = image_data.split(",", 1)
        except ValueError:
            return jsonify({"error": "Invalid image data"}), 400

        try:
            extracted_statistics = extract_from_image(base64_image)
        except OCRServiceError as exc:
            app.logger.error("Image processing failed: %s", exc)
            return jsonify({"error": PROCESSING_ERROR_MESSAGE}), 502

        if (
            isinstance(extracted_statistics, str)
            and "The provided image does not contain" in extracted_statistics
        ):
            return (
                "The provided image does not contain relevant textual information "
                "about an academic course or exam results to convert into JSON format"
            )

        return {
            "json": extracted_statistics,
            "html": json_to_html(dict(extracted_statistics)),
        }

    @app.route("/send", methods=["POST"])
    def send_data():
        if not request.is_json:
            return jsonify({"error": "Invalid Request sent"}), 400
        data = request.get_json(silent=True) or {}
        if "image" not in data or "data" not in data:
            return jsonify({"error": "Invalid Request sent"}), 400
        if not isinstance(data["data"], dict):
            return jsonify({"error": "Invalid Request sent"}), 400

        try:
            submission_id = repository.create_submission(
                data["image"], data["data"]
            )
        except ValueError:
            return jsonify({"error": "Invalid image data"}), 400
        if submission_id is None:
            return (
                jsonify(
                    {
                        "error": (
                            "These stats have already been sent once but haven't "
                            "been processed yet!"
                        )
                    }
                ),
                400,
            )

        _, pending = repository.pending_summary()
        legacy_entries = [
            {
                "data": item["data"],
                "timestamp": item["timestamp"],
                "processed": False,
            }
            for item in pending
        ]
        should_send_email, entries = check_send_email(legacy_entries)
        if should_send_email:
            try:
                send_email(mail, entries)
            except Exception:
                app.logger.exception("Review reminder email failed")

        return jsonify(
            {
                "message": "Data received and saved successfully",
                "submission_id": submission_id,
            }
        ), 200

    @app.route("/search", methods=["GET"])
    def search_html():
        query = request.args.get("query", "")
        if not query:
            return []
        try:
            hits = search_index.search(
                query,
                limit=INTERACTIVE_SEARCH_LIMIT,
                attributes=SEARCH_ATTRIBUTES,
            )["hits"]
        except SearchIndexError:
            app.logger.exception("Search failed")
            return jsonify({"error": "Search is temporarily unavailable"}), 503
        return [json_to_html(dict(hit), query=query) for hit in hits]

    @app.route("/suggest", methods=["GET"])
    def suggest_modules():
        query = request.args.get("query", "").strip()
        if not query:
            return []
        try:
            hits = search_index.search(
                query,
                limit=SUGGESTION_SEARCH_LIMIT,
                attributes=["Module Number", "Name", "Date"],
            )["hits"]
        except SearchIndexError:
            app.logger.exception("Module suggestions failed")
            return jsonify({"error": "Search is temporarily unavailable"}), 503

        modules = {}
        for rank, hit in enumerate(hits):
            module_number = str(hit.get("Module Number", "")).strip()
            if not module_number:
                continue
            key = module_number.casefold()
            date = str(hit.get("Date", ""))
            current = modules.get(key)
            if current is None:
                modules[key] = {
                    "module_number": module_number,
                    "name": str(hit.get("Name", "")),
                    "latest_date": date,
                    "exam_count": 1,
                    "_rank": rank,
                }
            else:
                current["exam_count"] += 1
                if date > current["latest_date"]:
                    current["latest_date"] = date
                    current["name"] = str(hit.get("Name", ""))

        query_key = query.casefold()

        def suggestion_order(module):
            module_key = module["module_number"].casefold()
            if module_key == query_key:
                module_match = 0
            elif module_key.startswith(query_key):
                module_match = 1
            elif query_key in module_key:
                module_match = 2
            else:
                module_match = 3
            return module_match, module["_rank"]

        suggestions = sorted(modules.values(), key=suggestion_order)
        for suggestion in suggestions:
            suggestion.pop("_rank")
        return suggestions[:SUGGESTION_LIMIT]

    @app.route("/search/module", methods=["GET"])
    def search_module():
        module_number = request.args.get("module", "").strip()
        if not module_number:
            return []
        try:
            hits = search_index.search(
                module_number,
                limit=MODULE_SEARCH_LIMIT,
                attributes=SEARCH_ATTRIBUTES,
            )["hits"]
        except SearchIndexError:
            app.logger.exception("Module search failed")
            return jsonify({"error": "Search is temporarily unavailable"}), 503

        exact_hits = [
            hit
            for hit in hits
            if str(hit.get("Module Number", "")).strip().casefold()
            == module_number.casefold()
        ]
        exact_hits.sort(key=lambda hit: str(hit.get("Date", "")), reverse=True)
        return [
            json_to_html(dict(hit), query=module_number)
            for hit in exact_hits
        ]

    @app.route("/check", methods=["POST"])
    def check_api():
        data = request.get_json(silent=True) or {}
        try:
            return search_index.search(data.get("query", ""), limit=1)
        except SearchIndexError:
            return jsonify({"error": "Search is temporarily unavailable"}), 503

    @app.route("/search", methods=["POST"])
    def search_api():
        data = request.get_json(silent=True) or {}
        try:
            return search_index.search(
                data.get("query", ""), limit=int(data.get("limit", 100000))
            )
        except (SearchIndexError, ValueError, TypeError):
            return jsonify({"error": "Search is temporarily unavailable"}), 503

    return app


app = create_public_app()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(port=6655, host="0.0.0.0")
