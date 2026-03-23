import os

import requests
from dotenv import load_dotenv


# Load environment variables from .env when present.
load_dotenv()


DEFAULT_RAG_API_BASE_URL = os.getenv("RAG_API_BASE_URL", "http://localhost:8000")


def query(
    query,
    user_id,
    app_name="doclens",
    doc_id=None,
    base_url=None,
    timeout=60,
    llm_config=None,
):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + "/query"

    payload = {
        "query": query,
        "user_id": user_id,
        "app_name": app_name,
    }

    if doc_id:
        payload["doc_id"] = doc_id

    if llm_config:
        payload["llm_config"] = llm_config

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
        files = {
            "file": (os.path.basename(file_path), file_handle),
        }
        response = requests.post(endpoint, data=data, files=files, timeout=timeout)

    response.raise_for_status()
    return response.json()


def generate(prompt, model=None, api_key=None, base_url=None, timeout=60):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + "/generate"

    payload = {
        "prompt": prompt,
    }

    if model:
        payload["model"] = model

    if api_key:
        payload["api_key"] = api_key

    response = requests.post(endpoint, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()
