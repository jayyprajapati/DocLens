import base64
import hashlib
import hmac
import json
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

DEFAULT_RAG_API_BASE_URL = os.getenv("CORTEX_BASE_URL", os.getenv("RAG_API_BASE_URL", "http://localhost:8000"))
_JWT_SECRET = os.getenv("CORTEX_JWT_SECRET", "dev-secret")


def _b64url(data):
    if isinstance(data, str):
        data = data.encode()
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _make_token(user_id):
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")))
    now = int(time.time())
    payload = _b64url(json.dumps({"sub": str(user_id), "iat": now, "exp": now + 3600}, separators=(",", ":")))
    msg = f"{header}.{payload}"
    sig = _b64url(hmac.new(_JWT_SECRET.encode(), msg.encode(), hashlib.sha256).digest())
    return f"{msg}.{sig}"


def _auth(user_id):
    return {"Authorization": f"Bearer {_make_token(user_id)}"}


def is_available(base_url=None, timeout=3):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + "/health"
    try:
        response = requests.get(endpoint, timeout=timeout)
        return response.ok
    except requests.RequestException:
        return False


def query(
    query,
    user_id,
    app_name="doclens",
    doc_id=None,
    doc_ids=None,
    base_url=None,
    timeout=120,
    llm=None,
    llm_config=None,
):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + "/chat"

    payload = {"query": query, "app_name": app_name}

    if doc_id and not doc_ids:
        doc_ids = [doc_id]
    if doc_ids:
        payload["doc_ids"] = [str(d) for d in doc_ids if str(d).strip()]

    if llm_config and not llm:
        llm = llm_config
    if llm:
        payload["llm"] = llm

    response = requests.post(
        endpoint, params={"stream": "false"}, json=payload, timeout=timeout, headers=_auth(user_id)
    )
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
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + "/chat"

    payload = {"query": query, "app_name": app_name}

    if thread_id:
        payload["thread_id"] = thread_id
    if doc_ids:
        payload["doc_ids"] = [str(d) for d in doc_ids if str(d).strip()]
    if llm:
        payload["llm"] = llm

    response = requests.post(
        endpoint, params={"stream": "false"}, json=payload, timeout=timeout, headers=_auth(user_id)
    )
    response.raise_for_status()
    return response.json()


def stream_chat(
    query,
    user_id,
    thread_id=None,
    app_name="doclens",
    doc_ids=None,
    base_url=None,
    timeout=120,
    llm=None,
):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + "/chat"

    payload = {"query": query, "app_name": app_name}

    if thread_id:
        payload["thread_id"] = thread_id
    if doc_ids:
        payload["doc_ids"] = [str(d) for d in doc_ids if str(d).strip()]
    if llm:
        payload["llm"] = llm

    response = requests.post(
        endpoint,
        params={"stream": "true"},
        json=payload,
        timeout=timeout,
        stream=True,
        headers={"Accept": "text/event-stream", **_auth(user_id)},
    )
    response.raise_for_status()
    return response


def generate(
    query,
    user_id,
    app_name="doclens",
    base_url=None,
    timeout=120,
    llm=None,
    context=None,
    task=None,
):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + "/generate"

    payload = {"query": query, "app_name": app_name}

    if context is not None:
        payload["context"] = context
    if task:
        payload["task"] = task
    if llm:
        payload["llm"] = llm

    response = requests.post(
        endpoint, params={"stream": "false"}, json=payload, timeout=timeout, headers=_auth(user_id)
    )
    response.raise_for_status()
    return response.json()


def list_threads(user_id, app_name="doclens", base_url=None, timeout=30):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + "/threads"
    response = requests.get(
        endpoint, params={"app_name": app_name}, timeout=timeout, headers=_auth(user_id)
    )
    response.raise_for_status()
    return response.json()


def get_thread(thread_id, user_id, base_url=None, timeout=30):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + f"/threads/{thread_id}"
    response = requests.get(endpoint, timeout=timeout, headers=_auth(user_id))
    response.raise_for_status()
    return response.json()


def delete_thread(thread_id, user_id, base_url=None, timeout=30):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + f"/threads/{thread_id}"
    response = requests.delete(endpoint, timeout=timeout, headers=_auth(user_id))
    response.raise_for_status()
    return response.json()


def patch_thread(thread_id, user_id, title=None, base_url=None, timeout=30):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + f"/threads/{thread_id}"
    payload = {}
    if title is not None:
        payload["title"] = title
    response = requests.patch(endpoint, json=payload, timeout=timeout, headers=_auth(user_id))
    response.raise_for_status()
    return response.json()


def ingest(file_path, user_id, app_name="doclens", base_url=None, timeout=120):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + "/ingest"

    # Do NOT set Content-Type — requests sets multipart/form-data with boundary automatically.
    with open(file_path, "rb") as file_handle:
        files = {"file": (os.path.basename(file_path), file_handle)}
        response = requests.post(
            endpoint,
            data={"app_name": app_name},
            files=files,
            timeout=timeout,
            headers=_auth(user_id),
        )

    response.raise_for_status()
    return response.json()


def delete_document(user_id, doc_id, app_name="doclens", base_url=None, timeout=120):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + "/delete"
    response = requests.post(
        endpoint,
        json={"doc_id": doc_id, "app_name": app_name},
        timeout=timeout,
        headers=_auth(user_id),
    )
    response.raise_for_status()
    return response.json()


def delete_all_documents(user_id, app_name="doclens", base_url=None, timeout=120):
    endpoint = (base_url or DEFAULT_RAG_API_BASE_URL).rstrip("/") + "/delete_all"
    response = requests.post(
        endpoint,
        json={"app_name": app_name},
        timeout=timeout,
        headers=_auth(user_id),
    )
    response.raise_for_status()
    return response.json()
