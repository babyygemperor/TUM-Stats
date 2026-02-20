from flask import Flask, request
from meilisearch import Client
import json
import requests

from shared.rendering import json_to_html

app = Flask(__name__)

client = Client('http://meilisearch:7700')

index = client.index('exams')


@app.after_request
def add_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query', '')
    if not query:
        return []

    search_results = index.search(query, {
        'attributesToRetrieve': ['Date', 'Module Number', 'Name', 'Registered',
                                  'Attempt made', 'Not present', 'Withdrawal with approved reasons',
                                  'Not valid/cheating', 'Rejection',
                                  'Average total', 'Average (assessed as passed)', 'Grade distribution'],
    })

    html = []

    for search_result in search_results['hits']:
        grades = search_result.pop('Grade distribution')
        search_result['Grade distribution'] = grades
        html.append(json_to_html(search_result, query=query))

    return html


@app.route('/check', methods=['POST'])
def check_api():
    data = request.json

    return requests.post('http://meilisearch:7700/indexes/exams/search', headers={'Content-Type': 'application/json'}, data=json.dumps({"q": data['query'], "limit": 1})).json()


@app.route('/search', methods=['POST'])
def search_api():
    data = request.json

    if 'limit' not in data.keys():
        data['limit'] = 100000

    return requests.post('http://meilisearch:7700/indexes/exams/search', headers={'Content-Type': 'application/json'}, data=json.dumps({"q": data['query'], "limit": data["limit"]})).json()


if __name__ == '__main__':
    app.run(port=6655, host="0.0.0.0")
