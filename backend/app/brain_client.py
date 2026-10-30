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


# One pooled client for the process: keep-alive connections to Brain instead of a new
# TCP (and, in production, TLS) handshake per call. httpx.Client is thread-safe.
_http: httpx.Client | None = None


def _client() -> httpx.Client:
    global _http
    if _http is None:
        _http = httpx.Client(
            base_url=settings.brain_base_url,
            timeout=httpx.Timeout(settings.brain_timeout, connect=10.0),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        )
    return _http


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
        resp = _client().request(method, path, headers=_headers(), **kwargs)
    except httpx.RequestError as exc:
        raise BrainError(f"could not reach Brain ({action}): {exc}", status=None) from exc
    _raise_for_status(resp, action)
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return {}


# ── Ingestion ────────────────────────────────────────────────────────────────


def ingest_text(*, text: str, doc_id: str, namespace: str, title: str) -> dict:
    """POST /v1/ingest. The ``title`` makes Brain embed and rerank every chunk as
    "title > heading" (contextual chunk headers), so a bare table row still carries
    the document it belongs to."""
    payload = {
        "app_name": settings.brain_app_name,
        "doc_id": doc_id,
        "namespace": namespace,
        "text": text,
        "dedup": False,
        "title": title[:200],
    }
    return _request("POST", "/v1/ingest", "ingest", json=payload)


# ── Retrieval (local embeddings — no BYOK key needed) ─────────────────────────


def retrieve(
    *, query: str, namespace: str, doc_ids: list[str] | None, top_k: int | None = None, top_n: int | None = None
) -> list[dict]:
    """POST /v1/retrieve → reranked chunks [{text, heading, title, score, rerank_score, doc_id, urls}]."""
    payload: dict = {"app_name": settings.brain_app_name, "query": query, "namespace": namespace}
    if doc_ids:
        payload["doc_ids"] = doc_ids
    payload["top_k"] = top_k or settings.retrieve_top_k
    if top_n:
        payload["top_n"] = top_n
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
    reasoning: str | None = None,
) -> dict:
    """POST /v1/generate with the caller's BYOK ``llm`` override. Returns
    {text, json?, usage?}. ``reasoning`` ("off|low|medium|high") only affects Ollama
    reasoning models and is ignored by older Brain builds.

    Hosted mode puts a ``_fallback`` model in ``llm``: if the primary model is rate-limited or
    down, the call is retried once on it and ``llm["_fell_back"]`` is set (keys starting with
    "_" are DocLens-private and never sent to Brain)."""
    wire = {k: v for k, v in llm.items() if not k.startswith("_")}
    if llm.get("_fell_back") and llm.get("_fallback"):
        wire["model"] = llm["_fallback"]  # primary already failed this turn; don't wait on it again
    payload: dict = {
        "app_name": settings.brain_app_name,
        "system": system,
        "prompt": prompt,
        "llm": wire,
        "response_format": response_format,
    }
    if data is not None:
        payload["data"] = data
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if temperature is not None:
        payload["temperature"] = temperature
    if reasoning:
        payload["reasoning"] = reasoning
    try:
        return _request("POST", "/v1/generate", "generation", json=payload)
    except BrainError as exc:
        fallback = llm.get("_fallback")
        # rate-limited, out of credits (402), not available / retired (403/404/410) or down:
        # another model on the same key can still answer. 400/401 would fail the same way.
        retryable = exc.status is None or exc.status >= 402
        if not fallback or not retryable or fallback == wire.get("model"):
            raise
        llm["_fell_back"] = True
        return _request("POST", "/v1/generate", "generation", json={**payload, "llm": {**wire, "model": fallback}})


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
