"""HTTP client for Brain (the application-agnostic RAG engine).

Every call carries Brain's bearer key and ``app_name`` (which selects DocLens'
dedicated Qdrant collection). Per-user isolation is enforced by passing
``namespace=user_id`` on ingest/retrieve/delete. The LLM is **BYOK**: the user's
``{provider, api_key, model}`` is forwarded as Brain's per-request ``llm``
override on every generation — DocLens never relies on Brain's own keys.
"""
from __future__ import annotations

import httpx

from .config import settings


class BrainError(Exception):
    """A Brain call failed. ``status`` is the upstream HTTP status (or None for
    connectivity failures); ``detail`` is a human-readable message."""

    def __init__(self, detail: str, *, status: int | None = None):
        super().__init__(detail)
        self.detail = detail
        self.status = status


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.brain_api_key}"}


def _client() -> httpx.Client:
    return httpx.Client(base_url=settings.brain_base_url, timeout=settings.brain_timeout)


def _raise_for_status(resp: httpx.Response, action: str) -> None:
    if resp.status_code < 400:
        return
    detail = resp.text
    try:
        body = resp.json()
        if isinstance(body, dict):
            detail = body.get("detail") or body.get("error") or detail
    except Exception:  # noqa: BLE001
        pass
    raise BrainError(f"{action} failed: {detail}", status=resp.status_code)


def _request(method: str, path: str, action: str, **kwargs) -> dict:
    try:
        with _client() as client:
            resp = client.request(method, path, headers=_headers(), **kwargs)
    except httpx.RequestError as exc:
        raise BrainError(f"could not reach Brain ({action}): {exc}", status=None) from exc
    _raise_for_status(resp, action)
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return {}


# ── Ingestion ────────────────────────────────────────────────────────────────


def extract_and_ingest(
    *, file_bytes: bytes, filename: str, content_type: str, doc_id: str, namespace: str
) -> dict:
    """POST /v1/extract with ingest=true. Brain extracts text (PDF/DOCX/MD),
    chunks, embeds, and stores vectors under (app_name, namespace, doc_id).
    Returns {text, char_count, doc_id, chunk_count, ...}."""
    files = {"file": (filename, file_bytes, content_type or "application/octet-stream")}
    data = {
        "app_name": settings.brain_app_name,
        "doc_id": doc_id,
        "namespace": namespace,
        "ingest": "true",
        "dedup": "false",
    }
    return _request("POST", "/v1/extract", "ingest", files=files, data=data)


# ── Retrieval (local embeddings — no BYOK key needed) ─────────────────────────


def retrieve(*, query: str, namespace: str, doc_ids: list[str] | None, top_k: int | None = None) -> list[dict]:
    """POST /v1/retrieve → reranked chunks [{text, heading, score, doc_id, urls}]."""
    payload: dict = {"app_name": settings.brain_app_name, "query": query, "namespace": namespace}
    if doc_ids:
        payload["doc_ids"] = doc_ids
    payload["top_k"] = top_k or settings.retrieve_top_k
    data = _request("POST", "/v1/retrieve", "retrieve", json=payload)
    return data.get("chunks", []) or []


# ── Generation (BYOK — the user's provider/key/model) ─────────────────────────


def generate(
    *,
    system: str,
    prompt: str,
    llm: dict,
    data=None,
    response_format: str = "text",
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> dict:
    """POST /v1/generate with the caller's BYOK ``llm`` override. Returns
    {text, json?}."""
    payload: dict = {
        "app_name": settings.brain_app_name,
        "system": system,
        "prompt": prompt,
        "llm": llm,
        "response_format": response_format,
    }
    if data is not None:
        payload["data"] = data
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if temperature is not None:
        payload["temperature"] = temperature
    return _request("POST", "/v1/generate", "generation", json=payload)


def ping(llm: dict) -> dict:
    """POST /v1/llm/ping — validate a BYOK key/provider/model."""
    return _request("POST", "/v1/llm/ping", "key check", json={"llm": llm})


# ── Deletion ─────────────────────────────────────────────────────────────────


def delete(*, doc_id: str | None = None, namespace: str | None = None) -> dict:
    """POST /v1/delete — remove vectors by doc_id and/or namespace."""
    payload: dict = {"app_name": settings.brain_app_name}
    if doc_id:
        payload["doc_id"] = doc_id
    if namespace:
        payload["namespace"] = namespace
    return _request("POST", "/v1/delete", "delete", json=payload)
