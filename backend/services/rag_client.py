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
    timeout=60,
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


def delete_document(user_id, doc_id, app_name="doclens", base_url=None, timeout=60):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + "/delete"

    payload = {"user_id": user_id, "doc_id": doc_id, "app_name": app_name}

    response = requests.post(endpoint, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def delete_all_documents(user_id, app_name="doclens", base_url=None, timeout=60):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + "/delete_all"

    payload = {"user_id": user_id, "app_name": app_name}

    response = requests.post(endpoint, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()
