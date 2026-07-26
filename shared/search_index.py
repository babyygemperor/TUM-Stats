import json
import os
import time

import requests


class SearchIndexError(Exception):
    pass


class SearchIndex:
    def __init__(self, base_url=None, api_key=None, index_name="exams"):
        self.base_url = (
            base_url or os.environ.get("MEILISEARCH_URL", "http://meilisearch:7700")
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("MEILI_MASTER_KEY")
        self.index_name = index_name

    @property
    def headers(self):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        return headers

    def wait_until_ready(self, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                response = requests.get(self.base_url + "/health", timeout=3)
                if response.ok:
                    return
            except requests.RequestException:
                pass
            time.sleep(1)
        raise SearchIndexError("Search service did not become ready")

    def ensure_index(self):
        response = requests.get(
            "{}/indexes/{}".format(self.base_url, self.index_name),
            headers=self.headers,
            timeout=10,
        )
        if response.status_code == 404:
            task = self._request_task(
                "POST",
                self.base_url + "/indexes",
                {"uid": self.index_name, "primaryKey": "id"},
            )
            self.wait_for_task(task)
        elif not response.ok:
            raise SearchIndexError(
                "Unable to inspect search index (HTTP {})".format(
                    response.status_code
                )
            )

    def delete_index(self):
        response = requests.delete(
            "{}/indexes/{}".format(self.base_url, self.index_name),
            headers=self.headers,
            timeout=15,
        )
        if response.status_code == 404:
            return
        if not response.ok:
            raise SearchIndexError(
                "Unable to delete search index (HTTP {})".format(
                    response.status_code
                )
            )
        task_uid = response.json().get("taskUid")
        if task_uid is not None:
            self.wait_for_task(task_uid)

    def upsert_documents(self, documents):
        if not documents:
            return
        task = self._request_task(
            "POST",
            "{}/indexes/{}/documents".format(self.base_url, self.index_name),
            documents,
        )
        self.wait_for_task(task)

    def search(self, query, limit=100000, attributes=None):
        payload = {"q": query, "limit": limit}
        if attributes:
            payload["attributesToRetrieve"] = attributes
        response = requests.post(
            "{}/indexes/{}/search".format(self.base_url, self.index_name),
            headers=self.headers,
            json=payload,
            timeout=15,
        )
        if not response.ok:
            raise SearchIndexError(
                "Search failed (HTTP {})".format(response.status_code)
            )
        return response.json()

    def _request_task(self, method, url, payload):
        response = requests.request(
            method, url, headers=self.headers, json=payload, timeout=30
        )
        if not response.ok:
            raise SearchIndexError(
                "Search update failed (HTTP {}): {}".format(
                    response.status_code, response.text[:500]
                )
            )
        task_uid = response.json().get("taskUid")
        if task_uid is None:
            raise SearchIndexError("Search update did not return a task ID")
        return task_uid

    def wait_for_task(self, task_uid, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = requests.get(
                "{}/tasks/{}".format(self.base_url, task_uid),
                headers=self.headers,
                timeout=10,
            )
            if not response.ok:
                raise SearchIndexError(
                    "Unable to inspect search task (HTTP {})".format(
                        response.status_code
                    )
                )
            task = response.json()
            if task["status"] == "succeeded":
                return task
            if task["status"] == "failed":
                raise SearchIndexError(
                    "Search task failed: {}".format(
                        json.dumps(task.get("error", {}), sort_keys=True)
                    )
                )
            time.sleep(0.1)
        raise SearchIndexError("Search task timed out")


def reconcile_outbox(repository, search_index):
    completed = 0
    failed = 0
    for job in repository.pending_outbox():
        try:
            if job["operation"] == "upsert":
                search_index.upsert_documents([json.loads(job["payload"])])
            else:
                raise SearchIndexError("Delete jobs are not implemented")
            repository.complete_outbox(job["id"])
            completed += 1
        except Exception as exc:
            repository.fail_outbox(job["id"], exc)
            failed += 1
    return {"completed": completed, "failed": failed}
