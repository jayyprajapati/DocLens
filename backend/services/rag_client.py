import os

import requests
from dotenv import load_dotenv

load_dotenv()

DEFAULT_RAG_API_BASE_URL = os.getenv("RAG_API_BASE_URL", "http://localhost:8000")


def query(
    query,
    user_id,
    app_name="doclens",
    doc_ids=None,
    base_url=None,
    timeout=120,
    llm=None,
):
    """
    llm: {"provider": "openai", "api_key": "...", "model": "gpt-4o-mini"}
    doc_ids: optional list of doc_id strings to scope retrieval
    """
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + "/query"

    payload = {
        "query": query,
        "user_id": user_id,
        "app_name": app_name,
    }

    if doc_ids:
        payload["doc_ids"] = [str(d) for d in doc_ids if str(d).strip()]

    if llm:
        payload["llm"] = llm

    response = requests.post(endpoint, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def chat(
    query,
    user_id,
    thread_id=None,
    app_name="doclens",
    doc_ids=None,
    base_url=None,
    timeout=120,
    llm=None,
):
    """Multi-turn chat call. If thread_id is None, Cortex creates a new thread."""
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + "/chat"

    payload = {
        "query": query,
        "user_id": user_id,
        "app_name": app_name,
    }

    if thread_id:
        payload["thread_id"] = thread_id
    if doc_ids:
        payload["doc_ids"] = [str(d) for d in doc_ids if str(d).strip()]
    if llm:
        payload["llm"] = llm

    response = requests.post(endpoint, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def list_threads(user_id, app_name="doclens", base_url=None, timeout=30):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + "/threads"
    response = requests.get(
        endpoint,
        params={"user_id": user_id, "app_name": app_name},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def get_thread(thread_id, user_id, base_url=None, timeout=30):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + f"/threads/{thread_id}"
    response = requests.get(endpoint, params={"user_id": user_id}, timeout=timeout)
    response.raise_for_status()
    return response.json()


def delete_thread(thread_id, user_id, base_url=None, timeout=30):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + f"/threads/{thread_id}"
    response = requests.delete(endpoint, params={"user_id": user_id}, timeout=timeout)
    response.raise_for_status()
    return response.json()


def patch_thread(thread_id, user_id, title=None, base_url=None, timeout=30):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + f"/threads/{thread_id}"
    payload = {}
    if title is not None:
        payload["title"] = title
    response = requests.patch(
        endpoint,
        params={"user_id": user_id},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def ingest(file_path, user_id, app_name="doclens", base_url=None, timeout=120):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + "/ingest"

    data = {
        "user_id": user_id,
        "app_name": app_name,
    }

    with open(file_path, "rb") as file_handle:
        files = {"file": (os.path.basename(file_path), file_handle)}
        response = requests.post(endpoint, data=data, files=files, timeout=timeout)

    response.raise_for_status()
    return response.json()


def delete_document(user_id, doc_id, app_name="doclens", base_url=None, timeout=120):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + "/delete"

    payload = {"user_id": user_id, "doc_id": doc_id, "app_name": app_name}

    response = requests.post(endpoint, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def delete_all_documents(user_id, app_name="doclens", base_url=None, timeout=120):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + "/delete_all"

    payload = {"user_id": user_id, "app_name": app_name}

    response = requests.post(endpoint, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()
