import os.path
import json

import requests
from flask import Flask, render_template, request, jsonify

from shared.rendering import json_to_html

app = Flask(__name__)

data_file = '/stats/new_data.json'
new_data_only = '/stats/new_data_only.json'
processed_data_legacy = '/stats/processed_data.json'

original_json_data = None
unprocessed_items = None


def migrate_processed_flags():
    """One-time migration: if processed_data.json exists, mark those entries
    as processed in new_data.json and remove the legacy file."""
    if not os.path.exists(processed_data_legacy) or not os.path.exists(data_file):
        return

    with open(processed_data_legacy, 'r') as file:
        processed_json_data = json.load(file)

    if not processed_json_data:
        return

    processed_timestamps = {item['timestamp'] for item in processed_json_data}

    with open(data_file, 'r') as file:
        all_data = json.load(file)

    changed = False
    for entry in all_data:
        if 'processed' not in entry and entry['timestamp'] in processed_timestamps:
            entry['processed'] = True
            changed = True
        elif 'processed' not in entry:
            entry['processed'] = False
            changed = True

    if changed:
        with open(data_file, 'w') as file:
            json.dump(all_data, file, indent=4)

    os.rename(processed_data_legacy, processed_data_legacy + '.bak')
    print(f"Migrated {len(processed_timestamps)} processed flags. Legacy file renamed to .bak", flush=True)


def load_data():
    global original_json_data, unprocessed_items

    migrate_processed_flags()

    try:
        with open(data_file, 'r') as file:
            original_json_data = json.load(file)
    except FileNotFoundError:
        original_json_data = []

    for items in original_json_data:
        if 'Module Number' not in items['data'].keys():
            items['data']['Module Number'] = ''

    unprocessed_items = [item for item in original_json_data if not item.get('processed', False)]


def tojson_pretty(value):
    return json.dumps(value, sort_keys=True,
                      indent=4, separators=(',', ': '))


@app.route('/')
def index():
    load_data()
    return render_template('index.html', items=unprocessed_items, enumerate=enumerate,
                           json_to_html=json_to_html,
                           tojson_pretty=tojson_pretty)


@app.route('/update/<timestamp>', methods=['POST'])
def update(timestamp):
    data = request.json
    updated = False
    updated_item = {}
    for item in original_json_data:
        if item['timestamp'] == timestamp:
            if 'Module Number' not in data['data'].keys() or len(data['data']['Module Number']) < 1:
                return jsonify(success=False, message="Module Number is invalid"), 400
            updated_item = item
            updated_item['data'] = data['data']
            updated_item['data']['id'] = data['data']['Module Number'] + "_" + data['data']['Date']
            updated_item['processed'] = True
            updated = True
            break

    if updated:
        url = 'http://meilisearch:7700/indexes/exams/documents'
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, headers=headers, json=updated_item['data'])
        print(response.json())
        taskUid = response.json()["taskUid"]

        if response.status_code == 202:
            response = requests.get(f'http://meilisearch:7700/tasks/{taskUid}')
            while response.json()['status'] == 'processing' or response.json()['status'] == 'enqueued':
                response = requests.get(f'http://meilisearch:7700/tasks/{taskUid}')
            print(response.json())

            if response.json()['status'] == 'failed':
                return jsonify(success=False, message=response.json()['error']['message']), 400

            # Save the processed flag back to new_data.json
            with open(data_file, 'w') as file:
                json.dump(original_json_data, file, indent=4)

            # Append to new_data_only.json for Meilisearch seeding
            if os.path.exists(new_data_only):
                with open(new_data_only, 'r') as file:
                    file_data = json.load(file)
                file_data.append(data['data'])
                with open(new_data_only, 'w') as file:
                    json.dump(file_data, file, indent=4)
            else:
                with open(new_data_only, 'w') as file:
                    json.dump([data['data']], file, indent=4)

            return jsonify(success=True, message="Data processed and sent successfully.")
        return jsonify(success=False, message="Data processed but failed to send."), 500
    return jsonify(success=False, message="Timestamp not found."), 404


if __name__ == '__main__':
    load_data()
    app.run(debug=True, port=9981, host="0.0.0.0")
