import os.path

import requests
from flask import Flask, render_template, request, jsonify
from html import escape
import json

app = Flask(__name__)

original_data = '/stats/new_data.json'
processed_data = '/stats/processed_data.json'
just_data = '/stats/new_data_only.json'
original_json_data = None
processed_json_data = None
unprocessed_items = None


def load_data():
    global original_json_data, processed_json_data, unprocessed_items
    try:
        with open(original_data, 'r') as file:
            original_json_data = json.load(file)
    except FileNotFoundError:
        original_json_data = []

    try:
        with open(processed_data, 'r') as file:
            processed_json_data = json.load(file)
    except FileNotFoundError:
        processed_json_data = []

    for items in original_json_data:
        if 'Module Number' not in items['data'].keys():
            items['data']['Module Number'] = ''

    processed_timestamps = {item['timestamp'] for item in processed_json_data}
    unprocessed_items = [item for item in original_json_data if item['timestamp'] not in processed_timestamps]


def json_to_html(json_data, query):
    def get_value(key, value, data):
        if key == 'Registered':
            return_value = 0
            for k, v in data['Grade distribution'].items():
                return_value += int(v)
            return return_value
        if key == 'Attempt made':
            return_value = 0
            for k, v in data['Grade distribution'].items():
                if k in ["1.0", "1.3", "1.7", "2.0", "2.3", "2.7", "3.0", "3.3", "3.7", "4.0", "4.3", "4.7", "5.0", "B pass", "B", "N fail", "N"]:
                    return_value += int(v)
            return return_value
        if key == 'Not present':
            return_value = 0
            for k, v in data['Grade distribution'].items():
                if k in ["5.0X", "5.0 X", "5.0 X Nicht erschienen", "5.0 X Nicht erschienen"]:
                    return_value += int(v)
            return return_value
        if key == 'Rejection':
            return_value = 0
            for k, v in data['Grade distribution'].items():
                if k in ["5.0Z", "5.0 Z", "5.0Z Zurückweisung", "5.0 Z Zurückweisung"]:
                    return_value += int(v)
            return return_value
        if key == 'Not valid/cheating':
            return_value = 0
            for k, v in data['Grade distribution'].items():
                if k in ["5.0U", "5.0 U", "5.0 Ungültig", "5.0U Ungültig", "5.0 U Ungültig",
                 "5.0 U Täuschung", "5.0U Täuschung", "5.0 U Ungültig/Täuschung", "5.0U Ungültig/Täuschung"]:
                    return_value += int(v)
            return return_value
        if key == 'Percent. of exams failed':
            passed = 0
            total_students = get_value('Registered', 0, data)
            for k, v in data['Grade distribution'].items():
                if k in ["1.0", "1.3", "1.7", "2.0", "2.3", "2.7", "3.0", "3.3", "3.7", "4.0", "B pass", "B"]:
                    passed += int(v)
            return f"{str(100.0 - round(passed / total_students * 100, 2))}%"
        if key == 'Average total':
            grade = 0
            total_students = get_value('Registered', 0, data)
            for k, v in data['Grade distribution'].items():
                if k.startswith("5.0"):
                    k = "5.0"
                try:
                    grade += (int(v) * float(k))
                except ValueError as e:
                    print(e)
            return round(grade / total_students, 3)
        if key == 'Average (assessed as passed)':
            grade = 0
            total_students = 0.0
            for k, v in data['Grade distribution'].items():
                if k in ["1.0", "1.3", "1.7", "2.0", "2.3", "2.7", "3.0", "3.3", "3.7", "4.0"]:
                    grade += (int(v) * float(k))
                    total_students += float(k)
            return round(grade / total_students, 3)
        return value

    def render_html(data, depth=0):
        html_content = ""
        distribution_html = ""
        if isinstance(data, dict):
            if depth == 0:
                title = data.get('Name', '')
                html_content += f"<h3>{title}</h3>\n"
                html_content += "<table>\n<tbody>\n"
            for key, value in data.items():
                if isinstance(value, dict) and key == "Grade distribution":
                    continue
                elif isinstance(value, dict):
                    continue
                else:
                    label_id = f"ST{abs(hash(key)) % 1000000000000}"
                    value = str(value)
                    html_content += f"<tr><td><label for='{label_id}'>{escape(str(key))}:</label></td>"
                    html_content += f"<td id='{label_id}'>{get_value(key, value, data)}</td></tr>\n"
            html_content += f"<tr><td colspan='2'>{escape(str('Grade distribution'))}: Percent % / grade\nK. = Number of candidates</td></tr>\n"
            distribution_html = render_distribution(data["Grade distribution"])
            if depth == 0:
                html_content += "</tbody>\n</table>\n"
        html_content += distribution_html
        return html_content

    def render_distribution(distribution):
        required_grades = ["1.0", "1.3", "1.7", "2.0", "2.3", "2.7", "3.0", "3.3", "3.7", "4.0", "4.3", "4.7", "5.0"]

        for grade in required_grades:
            if grade not in distribution:
                distribution[grade] = "0"

        total_candidates = sum(int(count) for count in distribution.values())
        html_content = '<div style="display: flex; flex-direction: row; align-items: flex-end; position: relative; margin-top:1em; margin-bottom:3em; padding-right:3em; margin-right:2em; margin-left:2em; width: auto; height: 24em; z-index: 100;">'

        html_content += '<div style="position: absolute; left: 0; height: 23em; width: 1px; background-color: black; bottom: 20px;"></div>'

        html_content += '<div style="position: absolute; width: 100%; height: 1px; background-color: black; bottom: 20px; left: 0;"></div>'

        grade_colours = {
            "1.0": "rgb(0,255,0)", "1.1": "rgb(12,255,0)", "1.2": "rgb(25,255,0)", "1.3": "rgb(38,255,0)",
            "1.4": "rgb(51,255,0)", "1.5": "rgb(63,255,0)", "1.6": "rgb(76,255,0)", "1.7": "rgb(89,255,0)",
            "1.8": "rgb(101,255,0)", "1.9": "rgb(114,255,0)", "2.0": "rgb(127,255,0)", "2.1": "rgb(140,255,0)",
            "2.2": "rgb(153,255,0)", "2.3": "rgb(165,255,0)", "2.4": "rgb(178,255,0)", "2.5": "rgb(191,255,0)",
            "2.6": "rgb(204,255,0)", "2.7": "rgb(216,255,0)", "2.8": "rgb(229,255,0)", "2.9": "rgb(242,255,0)",
            "3.0": "rgb(255,255,0)", "3.1": "rgb(255,242,0)", "3.2": "rgb(255,229,0)", "3.3": "rgb(255,216,0)",
            "3.4": "rgb(255,204,0)", "3.5": "rgb(255,191,0)", "3.6": "rgb(255,178,0)", "3.7": "rgb(255,165,0)",
            "3.8": "rgb(255,153,0)", "3.9": "rgb(255,140,0)", "4.0": "rgb(255,127,0)", "4.1": "rgb(255,114,0)",
            "4.2": "rgb(255,101,0)", "4.3": "rgb(255,89,0)", "4.4": "rgb(255,76,0)", "4.5": "rgb(255,63,0)",
            "4.6": "rgb(255,51,0)", "4.7": "rgb(255,38,0)", "4.8": "rgb(255,25,0)", "4.9": "rgb(255,12,0)",
            "5.0": "rgb(255,0,0)", "5.0X": "rgb(255,0,50)", "5.0 X": "rgb(255,0,50)",
            "5.0 X Nicht erschienen": "rgb(255,0,50)", "5.0X Nicht erschienen": "rgb(255,0,50)",
            "5.0U": "rgb(255,0,50)", "5.0 U": "rgb(255,0,50)",
            "5.0 Ungültig": "rgb(255,0,50)", "5.0U Ungültig": "rgb(255,0,50)", "5.0 U Ungültig": "rgb(255,0,50)",
            "5.0 U Täuschung": "rgb(255,0,50)", "5.0U Täuschung": "rgb(255,0,50)",
            "5.0 U Ungültig/Täuschung": "rgb(255,0,50)", "5.0U Ungültig/Täuschung": "rgb(255,0,50)",
            "5.0Z": "rgb(255,0,50)", "5.0 Z": "rgb(255,0,50)",
            "5.0Z Zurückweisung": "rgb(255,0,50)", "5.0 Z Zurückweisung": "rgb(255,0,50)",
            "Unknown": "rgb(100,100,100)"
        }

        first = True

        distribution = dict(sorted(distribution.items()))

        for grade, count in distribution.items():
            try:
                percentage = (int(count) / total_candidates) * 100
                bar_height = f"{int(count) / int(max(distribution.values(), key=int)) * 20}em"
            except ZeroDivisionError:
                percentage = 0
                bar_height = 0
            colour = grade_colours.get(grade, "rgb(100,100,100)")
            if first:
                html_content += '<div style="width: 20%; margin: 0 0 0 1%; position: relative;">'
                first = False
            else:
                html_content += '<div style="width: 20%; position: relative;">'

            html_content += f'<div style="position: absolute; margin-left: 0; width: 100%; margin-top: 3.0em; height: {bar_height}; background-color: {colour}; bottom: 21px; z-index: 101">'
            if percentage > 0:
                html_content += f'<div style="color: black; text-align: center; position: absolute; bottom: 100%; width: 100%; margin-bottom: 1.0em">{percentage:.2f}%<br>{count} K.</div></div>'
            else:
                html_content += f'<div style="color: black; text-align: center; position: absolute; bottom: 100%; width: 100%; margin-bottom: 2.0em"><br>{count} K.</div></div>'
            html_content += f'<div style="position: absolute; width: 100%; text-align: center; margin-top: -1em;">{escape(str(grade))}</div>'
            html_content += '</div>'
        html_content += '</div>'
        return html_content

    keys = ['Registered', 'Attempt made', 'Not present', 'Not valid/cheating', 'Rejection',
            'Percent. of exams passed', 'Average total', 'Average (assessed as passed)']

    for key in keys:
        if key not in json_data:
            json_data[key] = None

    return render_html(json_data)


def tojson_pretty(value):
    return json.dumps(value, sort_keys=True,
                      indent=4, separators=(',', ': '))


@app.route('/')
def index():
    load_data()
    return render_template('index.html', items=unprocessed_items, enumerate=enumerate, json_to_html=json_to_html,
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
            updated_item['processed'] = 'true'
            updated = True
            break

    if updated:
        # Send data to external service using requests
        url = 'http://meilisearch:7700/indexes/exams/documents'
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, headers=headers, json=updated_item['data'])
        print(response.json())
        taskUid = response.json()["taskUid"]

        # Check response status and handle appropriately
        if response.status_code == 202:
            response = requests.get(f'http://meilisearch:7700/tasks/{taskUid}')
            while response.json()['status'] == 'processing' or response.json()['status'] == 'enqueued':
                response = requests.get(f'http://meilisearch:7700/tasks/{taskUid}')
            print(response.json())

            if response.json()['status'] == 'failed':
                return jsonify(success=False, message=response.json()['error']['message']), 400

            if os.path.exists(processed_data):
                with open(processed_data, 'r') as file:
                    file_data = json.load(file)
                file_data.append(updated_item)
                with open(processed_data, 'w') as file:
                    json.dump(file_data, file, indent=4)
            else:
                with open(processed_data, 'w') as file:
                    json.dump([updated_item], file, indent=4)


            if os.path.exists(just_data):
                with open(just_data, 'r') as file:
                    file_data = json.load(file)
                file_data.append(data['data'])
                with open(just_data, 'w') as file:
                    json.dump(file_data, file, indent=4)
            else:
                with open(just_data, 'w') as file:
                    json.dump([data['data']], file, indent=4)

            return jsonify(success=True, message="Data processed and sent successfully.")
        return jsonify(success=False, message="Data processed but failed to send."), 500
    return jsonify(success=False, message="Timestamp not found."), 404


if __name__ == '__main__':
    load_data()
    app.run(debug=True, port=9981, host="0.0.0.0")
