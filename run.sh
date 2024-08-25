#!/bin/bash

git pull

docker compose down

docker compose up -d --no-deps --build

CONTAINER_ID=$(docker ps | grep tum-stats-meilisearch | awk '{print $1;}')

docker cp master_with_id.json $CONTAINER_ID:/meili_data
docker cp private-review/new_data_only.json $CONTAINER_ID:/meili_data

sleep 5

docker exec $CONTAINER_ID curl -X POST 'http://localhost:7700/indexes/exams/documents' -H 'Content-Type: application/json' --data-binary @master_with_id.json
docker exec $CONTAINER_ID curl -X POST 'http://localhost:7700/indexes/exams/documents' -H 'Content-Type: application/json' --data-binary @new_data_only.json