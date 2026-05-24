"""
Cortex v0 client for DocLens.

Env vars (read at module load):
    CORTEX_BASE_URL      – default http://localhost:8000
    CORTEX_API_KEY       – static bearer token sent to Cortex
    CORTEX_WORKSPACE_ID  – default workspace id
"""

from __future__ import annotations

import os
from typing import Optional, Union

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL: str = os.getenv("CORTEX_BASE_URL", os.getenv("RAG_API_BASE_URL", "http://localhost:8000"))
API_KEY: str = os.getenv("CORTEX_API_KEY", "")
WORKSPACE_ID: str = os.getenv("CORTEX_WORKSPACE_ID", "default")


# ---------------------------------------------------------------------------
# CortexClient
# ---------------------------------------------------------------------------

class CortexClient:
    """Async HTTP client for the Cortex v0 API."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        api_key: str = API_KEY,
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self, user_id: str) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "X-Cortex-User": user_id,
        }

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def is_available(self) -> bool:
        """GET /healthz → True if Cortex is reachable and healthy."""
        try:
            resp = await self._client.get("/healthz")
            return resp.is_success
        except httpx.RequestError:
            return False

    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------

    async def store_credential(self, user_id: str, provider: str, api_key: str) -> None:
        """PUT /v1/credentials – store a provider API key for a user."""
        resp = await self._client.put(
            "/v1/credentials",
            json={"provider": provider, "api_key": api_key},
            headers=self._headers(user_id),
        )
        resp.raise_for_status()

    async def ping_credential(self, user_id: str, provider: str) -> dict:
        """POST /v1/credentials/{provider}/ping → {ok, message}."""
        resp = await self._client.post(
            f"/v1/credentials/{provider}/ping",
            headers=self._headers(user_id),
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    async def ingest(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: str,
        workspace_id: str,
        scope_kind: str = "workspace",
        scope_id: Optional[str] = None,
    ) -> str:
        """
        POST /v1/documents (multipart) → document_id string.

        scope_kind: "thread" | "workspace"
        scope_id:   overrides scope_kind+workspace when provided
        """
        data: dict = {
            "workspace_id": workspace_id,
            "scope_kind": scope_kind,
        }
        if scope_id is not None:
            data["scope_id"] = scope_id

        files = {"file": (filename, file_bytes)}
        resp = await self._client.post(
            "/v1/documents",
            data=data,
            files=files,
            headers=self._headers(user_id),
        )
        resp.raise_for_status()
        body = resp.json()
        # Accept any of the common id field names returned by Cortex.
        for key in ("document_id", "doc_id", "id"):
            val = body.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        raise ValueError(f"Cortex ingest response missing document_id: {body!r}")

    async def delete_document(self, user_id: str, document_id: str) -> None:
        """DELETE /v1/documents/{document_id} – silently ignores 404."""
        resp = await self._client.delete(
            f"/v1/documents/{document_id}",
            headers=self._headers(user_id),
        )
        if resp.status_code == 404:
            return
        resp.raise_for_status()

    async def list_documents(
        self,
        user_id: str,
        workspace_id: str,
        scope_kind: Optional[str] = None,
        scope_id: Optional[str] = None,
    ) -> list[dict]:
        """GET /v1/documents → list of document dicts."""
        params: dict = {"workspace_id": workspace_id}
        if scope_kind is not None:
            params["scope_kind"] = scope_kind
        if scope_id is not None:
            params["scope_id"] = scope_id

        resp = await self._client.get(
            "/v1/documents",
            params=params,
            headers=self._headers(user_id),
        )
        resp.raise_for_status()
        body = resp.json()
        if isinstance(body, list):
            return body
        return body.get("documents", body.get("items", []))

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    async def chat(
        self,
        user_id: str,
        message: str,
        workspace_id: str,
        thread_id: Optional[str] = None,
        stream: bool = False,
    ) -> Union[dict, httpx.Response]:
        """
        POST /v1/chat

        stream=False → return parsed JSON dict
        stream=True  → return the raw streaming httpx.Response (caller iterates SSE)
        """
        payload: dict = {
            "workspace_id": workspace_id,
            "message": message,
            "stream": stream,
        }
        if thread_id is not None:
            payload["thread_id"] = thread_id

        if stream:
            req = self._client.build_request(
                "POST",
                "/v1/chat",
                json=payload,
                headers={
                    **self._headers(user_id),
                    "Accept": "text/event-stream",
                },
            )
            resp = await self._client.send(req, stream=True)
            resp.raise_for_status()
            return resp
        else:
            resp = await self._client.post(
                "/v1/chat",
                json=payload,
                headers=self._headers(user_id),
            )
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # Threads
    # ------------------------------------------------------------------

    async def create_thread(
        self,
        user_id: str,
        workspace_id: str,
        title: Optional[str] = None,
    ) -> dict:
        """POST /v1/threads → {id, title, ...}."""
        payload: dict = {"workspace_id": workspace_id}
        if title is not None:
            payload["title"] = title

        resp = await self._client.post(
            "/v1/threads",
            json=payload,
            headers=self._headers(user_id),
        )
        resp.raise_for_status()
        return resp.json()

    async def get_thread(self, user_id: str, thread_id: str) -> dict:
        """GET /v1/threads/{thread_id} → thread dict."""
        resp = await self._client.get(
            f"/v1/threads/{thread_id}",
            headers=self._headers(user_id),
        )
        resp.raise_for_status()
        return resp.json()

    async def list_threads(self, user_id: str, workspace_id: str) -> list[dict]:
        """GET /v1/threads?workspace_id= → list of thread dicts."""
        resp = await self._client.get(
            "/v1/threads",
            params={"workspace_id": workspace_id},
            headers=self._headers(user_id),
        )
        resp.raise_for_status()
        body = resp.json()
        if isinstance(body, list):
            return body
        return body.get("threads", body.get("items", []))

    async def delete_thread(self, user_id: str, thread_id: str) -> None:
        """DELETE /v1/threads/{thread_id} – silently ignores 404."""
        resp = await self._client.delete(
            f"/v1/threads/{thread_id}",
            headers=self._headers(user_id),
        )
        if resp.status_code == 404:
            return
        resp.raise_for_status()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def aclose(self) -> None:
        await self._client.aclose()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

cortex = CortexClient()


# ---------------------------------------------------------------------------
# Legacy shim – keeps existing callers in ingest_service, query_service,
# delete_service, and routes.py working without changes.
# ---------------------------------------------------------------------------

import asyncio as _asyncio
import requests as _requests
import base64 as _base64
import hashlib as _hashlib
import hmac as _hmac
import json as _json
import time as _time


_DEFAULT_BASE_URL = BASE_URL
_JWT_SECRET = os.getenv("CORTEX_JWT_SECRET", "dev-secret")


def _b64url(data):
    if isinstance(data, str):
        data = data.encode()
    return _base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _make_token(user_id):
    header = _b64url(_json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")))
    now = int(_time.time())
    payload = _b64url(
        _json.dumps({"sub": str(user_id), "iat": now, "exp": now + 3600}, separators=(",", ":"))
    )
    msg = f"{header}.{payload}"
    sig = _b64url(_hmac.new(_JWT_SECRET.encode(), msg.encode(), _hashlib.sha256).digest())
    return f"{msg}.{sig}"


def _auth(user_id):
    return {"Authorization": f"Bearer {_make_token(user_id)}"}


# -- health --

def is_available(base_url=None, timeout=3):
    endpoint = (base_url or _DEFAULT_BASE_URL).rstrip("/") + "/healthz"
    try:
        response = _requests.get(endpoint, timeout=timeout)
        return response.ok
    except _requests.RequestException:
        return False


# -- query / chat --

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
    endpoint = (base_url or _DEFAULT_BASE_URL).rstrip("/") + "/chat"
    payload = {"query": query, "app_name": app_name}
    if doc_id and not doc_ids:
        doc_ids = [doc_id]
    if doc_ids:
        payload["doc_ids"] = [str(d) for d in doc_ids if str(d).strip()]
    if llm_config and not llm:
        llm = llm_config
    if llm:
        payload["llm"] = llm
    response = _requests.post(
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
    endpoint = (base_url or _DEFAULT_BASE_URL).rstrip("/") + "/chat"
    payload = {"query": query, "app_name": app_name}
    if thread_id:
        payload["thread_id"] = thread_id
    if doc_ids:
        payload["doc_ids"] = [str(d) for d in doc_ids if str(d).strip()]
    if llm:
        payload["llm"] = llm
    response = _requests.post(
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
    endpoint = (base_url or _DEFAULT_BASE_URL).rstrip("/") + "/chat"
    payload = {"query": query, "app_name": app_name}
    if thread_id:
        payload["thread_id"] = thread_id
    if doc_ids:
        payload["doc_ids"] = [str(d) for d in doc_ids if str(d).strip()]
    if llm:
        payload["llm"] = llm
    response = _requests.post(
        endpoint,
        params={"stream": "true"},
        json=payload,
        timeout=timeout,
        stream=True,
        headers={"Accept": "text/event-stream", **_auth(user_id)},
    )
    response.raise_for_status()
    return response


# -- threads --

def list_threads(user_id, app_name="doclens", base_url=None, timeout=30):
    endpoint = (base_url or _DEFAULT_BASE_URL).rstrip("/") + "/threads"
    response = _requests.get(
        endpoint, params={"app_name": app_name}, timeout=timeout, headers=_auth(user_id)
    )
    response.raise_for_status()
    return response.json()


def get_thread(thread_id, user_id, base_url=None, timeout=30):
    endpoint = (base_url or _DEFAULT_BASE_URL).rstrip("/") + f"/threads/{thread_id}"
    response = _requests.get(endpoint, timeout=timeout, headers=_auth(user_id))
    response.raise_for_status()
    return response.json()


def delete_thread(thread_id, user_id, base_url=None, timeout=30):
    endpoint = (base_url or _DEFAULT_BASE_URL).rstrip("/") + f"/threads/{thread_id}"
    response = _requests.delete(endpoint, timeout=timeout, headers=_auth(user_id))
    response.raise_for_status()
    return response.json()


def patch_thread(thread_id, user_id, title=None, base_url=None, timeout=30):
    endpoint = (base_url or _DEFAULT_BASE_URL).rstrip("/") + f"/threads/{thread_id}"
    payload = {}
    if title is not None:
        payload["title"] = title
    response = _requests.patch(endpoint, json=payload, timeout=timeout, headers=_auth(user_id))
    response.raise_for_status()
    return response.json()


# -- documents --

def ingest(file_path, user_id, app_name="doclens", base_url=None, timeout=120):
    endpoint = (base_url or _DEFAULT_BASE_URL).rstrip("/") + "/ingest"
    import os as _os
    with open(file_path, "rb") as fh:
        files = {"file": (_os.path.basename(file_path), fh)}
        response = _requests.post(
            endpoint,
            data={"app_name": app_name},
            files=files,
            timeout=timeout,
            headers=_auth(user_id),
        )
    response.raise_for_status()
    return response.json()


def delete_document(user_id, doc_id, app_name="doclens", base_url=None, timeout=120):
    endpoint = (base_url or _DEFAULT_BASE_URL).rstrip("/") + "/delete"
    response = _requests.post(
        endpoint,
        json={"doc_id": doc_id, "app_name": app_name},
        timeout=timeout,
        headers=_auth(user_id),
    )
    response.raise_for_status()
    return response.json()


def delete_all_documents(user_id, app_name="doclens", base_url=None, timeout=120):
    endpoint = (base_url or _DEFAULT_BASE_URL).rstrip("/") + "/delete_all"
    response = _requests.post(
        endpoint,
        json={"app_name": app_name},
        timeout=timeout,
        headers=_auth(user_id),
    )
    response.raise_for_status()
    return response.json()
