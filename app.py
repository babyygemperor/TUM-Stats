from flask import Flask, request
from meilisearch import Client
from html import escape
import requests

app = Flask(__name__)

client = Client('http://meilisearch:7700')

index = client.index('exams')


@app.after_request
def add_headers(response):
    """
    Decorator function to add headers to the response.
    Allows cross-origin resource sharing (CORS) by setting the 'Access-Control-Allow-Origin',
    'Access-Control-Allow-Methods', and 'Access-Control-Allow-Headers' headers.
    """
    response.headers['Access-Control-Allow-Origin'] = '*'  # Allow requests from any origin
    response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'  # Allow POST and OPTIONS methods
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'  # Allow 'Content-Type' header
    return response


@app.route('/', methods=['GET'])
def main():
    return '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Stats</title>
        <style>
            body {
                font-family: Helvetica;
                margin: 20px;
                background-color: #f4f4f4;
            }
            .search-container {
                display: flex;
                justify-content: space-between;
                margin-bottom: 20px;
            }
            #searchBox {
                flex-grow: 1; /* Takes up remaining space */
                margin-right: 10px; /* Space between the search bar and button */
                padding: 10px;
                font-size: 16px;
                border: 2px solid #ccc;
                border-radius: 10px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            }
            #contributeButton {
                padding: 10px 20px;
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 10px;
                cursor: pointer;
                box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            }
            .stats {
                margin-top: 20px;
                background: white;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
        </style>
    </head>
    <body>
        <div class="search-container">
            <input type="text" id="searchBox" onkeyup="searchExams()" placeholder="Enter exam code or name">
            <button id="contributeButton" onclick="location.href='/upload'">Contribute your stats</button>
        </div>
        <div id="html-output"></div>

        <script>
            function searchExams() {
                const input = document.getElementById('searchBox');

                fetch(`/search?query=${encodeURIComponent(input.value)}`)
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById("html-output").innerHTML = '';
                        data.forEach(element => {
                            const div = document.createElement('div');
                            div.classList.add('stats');
                            div.innerHTML = element;
                            document.getElementById('html-output').appendChild(div);
                        });
                    })
                    .catch(error => console.error('Error:', error));
            }
        </script>
    </body>
    </html>
    '''


def json_to_html(json_data):
    def render_html(data, depth=0):
        html_content = ""
        distribution_html = ""
        if isinstance(data, dict):
            if depth == 0:
                title = f"{data.get('Name', '')}"
                html_content += f"<h3>{escape(title)}</h3>\n"
                html_content += "<table>\n<tbody>\n"
            for key, value in data.items():
                if isinstance(value, dict) and key == "Grade distribution":
                    html_content += f"<tr><td colspan='2'>{escape(str(key))}: Percent % / grade\nK. = Number of candidates</td></tr>\n"
                    distribution_html = render_distribution(value)
                elif isinstance(value, dict):
                    continue
                else:
                    label_id = f"ST{abs(hash(key)) % 1000000000000}"
                    html_content += f"<tr><td><label for='{label_id}'>{escape(str(key))}:</label></td>"
                    html_content += f"<td id='{label_id}'>{escape(str(value))}</td></tr>\n"
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
            "5.0": "rgb(255,0,0)", "5.0X": "rgb(255,0,50)", "5.0U": "rgb(255,0,50)", "5.0Z": "rgb(255,0,50)",
            "Unknown": "rgb(100,100,100)"
        }

        first = True

        distribution = dict(sorted(distribution.items()))

        for grade, count in distribution.items():
            percentage = (int(count) / total_candidates) * 100
            bar_height = f"{int(count) / int(max(distribution.values(), key=int)) * 20}em"
            colour = grade_colours.get(grade, "rgb(100,100,100)")
            if first:
                html_content += '<div style="width: 5%; margin: 0 0 0 1%; position: relative;">'
                first = False
            else:
                html_content += '<div style="width: 5%; position: relative;">'

            html_content += f'<div style="position: absolute; margin-left: 0; width: 100%; margin-top: 3.0em; height: {bar_height}; background-color: {colour}; bottom: 21px; z-index: 101">'
            if percentage > 0:
                html_content += f'<div style="color: black; text-align: center; position: absolute; bottom: 100%; width: 100%; margin-bottom: 1.0em">{percentage:.2f}%<br>{count} K.</div></div>'
            else:
                html_content += f'<div style="color: black; text-align: center; position: absolute; bottom: 100%; width: 100%; margin-bottom: 2.0em"><br>{count} K.</div></div>'
            html_content += f'<div style="text-align: center; margin-top: 25px;">{escape(str(grade))}</div>'
            html_content += '</div>'
        html_content += '</div>'
        return html_content

    return render_html(json_data)


@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query', '')
    if not query:
        return []

    search_results = index.search(query, {
        'attributesToRetrieve': ['Date', 'Module Number', 'Name', 'Registered',
                                  'Attempt made', 'Not present', 'Withdrawal with approved reasons',
                                  'Not valid/cheating', 'Rejection', 'Percent. of exams assessed as failed',
                                  'Average total', 'Average (assessed as passed)', 'Grade distribution'],
    })

    html = []

    for search_result in search_results['hits']:
        grades = search_result.pop('Grade distribution')
        search_result['Grade distribution'] = grades
        html.append(json_to_html(search_result))

    return html


@app.route('/search', methods=['POST'])
def search_api():
    data = request.json

    search_results = index.search(data['query'], {
        'attributesToRetrieve': ['Date', 'Module Number', 'Name', 'Registered',
                                  'Attempt made', 'Not present', 'Withdrawal with approved reasons',
                                  'Not valid/cheating', 'Rejection', 'Percent. of exams assessed as failed',
                                  'Average total', 'Average (assessed as passed)', 'Grade distribution'],
    })

    if 'limit' not in data.keys():
        data['limit'] = 100000

    return requests.post('http://meilisearch:7700', headers={'Content-Type': 'application/json'}, data={"q": data['query'], "limit": data["limit"]}).text


if __name__ == '__main__':
    app.run(port=6655, host="0.0.0.0")
