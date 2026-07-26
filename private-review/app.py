import json
import logging
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from shared.rendering import json_to_html
from shared.search_index import SearchIndex, SearchIndexError
from shared.storage import StatsRepository


def create_review_app(repository=None, search_index=None):
    template_folder = Path(__file__).resolve().parent / "templates"
    app = Flask(__name__, template_folder=str(template_folder))
    repository = repository or StatsRepository()
    repository.initialize()
    search_index = search_index or SearchIndex()

    def tojson_pretty(value):
        return json.dumps(
            value, sort_keys=True, indent=4, separators=(",", ": ")
        )

    @app.route("/health")
    def health():
        return {"status": "ok"}

    @app.route("/")
    def index():
        pending = repository.list_pending_submissions()
        items = []
        for item in pending:
            view_item = dict(item)
            view_item["image"] = "/submission-image/" + item["id"]
            view_item["data"].setdefault("Module Number", "")
            view_item["data"].setdefault("Date", "")
            items.append(view_item)
        return render_template(
            "index.html",
            items=items,
            enumerate=enumerate,
            json_to_html=json_to_html,
            tojson_pretty=tojson_pretty,
        )

    @app.route("/submission-image/<path:submission_id>")
    def submission_image(submission_id):
        submission = repository.get_submission(submission_id)
        if not submission or not submission["image_path"]:
            return jsonify({"error": "Image not found"}), 404
        image_path = (repository.image_dir / submission["image_path"]).resolve()
        image_root = repository.image_dir.resolve()
        if image_root not in image_path.parents:
            return jsonify({"error": "Image not found"}), 404
        return send_file(str(image_path))

    @app.route("/check", methods=["POST"])
    def check_duplicate():
        data = request.get_json(silent=True) or {}
        try:
            return search_index.search(data.get("query", ""), limit=1)
        except SearchIndexError:
            return jsonify({"error": "Search is temporarily unavailable"}), 503

    @app.route("/preview", methods=["POST"])
    def preview():
        data = (request.get_json(silent=True) or {}).get("data")
        if not isinstance(data, dict):
            return jsonify(success=False, message="Invalid data"), 400
        if not isinstance(data.get("Grade distribution"), dict):
            return (
                jsonify(
                    success=False,
                    message="Grade distribution must be a JSON object.",
                ),
                400,
            )
        try:
            return jsonify(success=True, html=json_to_html(dict(data)))
        except (KeyError, TypeError, ValueError):
            return (
                jsonify(
                    success=False,
                    message="The statistics contain invalid values.",
                ),
                400,
            )

    @app.route("/update/<path:submission_id>", methods=["POST"])
    def update(submission_id):
        payload = request.get_json(silent=True) or {}
        data = payload.get("data")
        if not isinstance(data, dict):
            return jsonify(success=False, message="Invalid data"), 400

        try:
            approved_data, outbox_id = repository.approve_submission(
                submission_id, data
            )
        except ValueError as exc:
            return jsonify(success=False, message=str(exc)), 400
        except KeyError:
            return jsonify(success=False, message="Submission not found"), 404

        try:
            search_index.upsert_documents([approved_data])
            repository.complete_outbox(outbox_id)
        except Exception as exc:
            repository.fail_outbox(outbox_id, exc)
            app.logger.exception("Approved record is pending search indexing")
            return (
                jsonify(
                    success=False,
                    message=(
                        "Data was approved, but search indexing is pending retry."
                    ),
                ),
                502,
            )

        return jsonify(
            success=True, message="Data processed and sent successfully."
        )

    return app


app = create_review_app()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(port=9981, host="0.0.0.0")
