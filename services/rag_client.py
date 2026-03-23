import os

import requests
from dotenv import load_dotenv


# Load environment variables from .env when present.
load_dotenv()


DEFAULT_RAG_API_BASE_URL = os.getenv("RAG_API_BASE_URL", "http://localhost:8000")


def query(query, user_id, app_name="doclens", doc_id=None, base_url=None, timeout=60):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + "/query"

    payload = {
        "query": query,
        "user_id": user_id,
        "app_name": app_name,
    }

    if doc_id:
        payload["doc_id"] = doc_id

    response = requests.post(endpoint, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()
