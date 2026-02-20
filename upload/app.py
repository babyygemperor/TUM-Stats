import os
import json
import datetime

from flask import Flask, request, jsonify
from ocr import extract_from_image
from email_service import configure_mail, check_send_email, send_email
from shared.rendering import json_to_html

app = Flask(__name__)
mail = configure_mail(app)

data_file = '/stats/new_data.json'


@app.after_request
def add_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


@app.route('/upload', methods=['POST'])
def upload_file():
    image_data = request.form['image']
    if not image_data:
        return jsonify({"error": "No image data"})

    _, base64_image = image_data.split(",", 1)

    print(len(base64_image))

    try:
        openai_response = extract_from_image(base64_image)
    except json.JSONDecodeError:
        return "An error occurred. Try again!"

    print(openai_response, flush=True)

    if isinstance(openai_response, str) and "The provided image does not contain" in openai_response:
        return "The provided image does not contain relevant textual information about an academic course or exam results to convert into JSON format"

    return {'json': openai_response, 'html': json_to_html(openai_response)}


def save_to_file(data):
    data['timestamp'] = datetime.datetime.utcnow().isoformat()
    data['processed'] = False
    if os.path.exists(data_file):
        with open(data_file, 'r') as file:
            file_data = json.load(file)
            file_data.append(data)
        with open(data_file, 'w') as file:
            json.dump(file_data, file, indent=4)
    else:
        file_data = [data]
        with open(data_file, 'w') as file:
            json.dump(file_data, file, indent=4)

    should_send_email, entries = check_send_email(file_data)
    return should_send_email, entries


def ordered(obj):
    if isinstance(obj, dict):
        return sorted((k, ordered(v)) for k, v in obj.items())
    if isinstance(obj, list):
        return sorted(ordered(x) for x in obj)
    else:
        return obj


def exists(data):
    if os.path.exists(data_file):
        with open(data_file, 'r') as file:
            file_data = json.load(file)
            for stat in file_data:
                if ordered(data['data']) == ordered(stat['data']) or data['data'] == stat['data']:
                    return True
    else:
        return False


@app.route('/send', methods=['POST'])
def send_data():
    if request.is_json:
        data = request.get_json()
        if 'image' in data.keys() and 'data' in data.keys():
            print(data['data'], flush=True)
            if exists(data):
                return jsonify({'error': 'These stats have already been sent once but haven\'t been processed yet!'}), 400
            should_send_email, entries = save_to_file(data)
            if should_send_email:
                send_email(mail, entries)
            return jsonify({'message': 'Data received and saved successfully'}), 200
        return jsonify({'error': 'Invalid Request sent'}), 400


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8079)
