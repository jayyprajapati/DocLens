"""DocLens HTTP API.

A thin orchestration + state layer: validates requests, resolves the user, owns
chat-session/document state in Mongo, and delegates all RAG/LLM work to Brain.

Two ways to chat:
  * **hosted** (``provider="hosted"``) — free mode on the server's Ollama Cloud key, with the
    admin-chosen model, daily per-user / per-IP / global quotas and a kill switch;
  * **BYOK** — the user's own provider key, forwarded per request and never stored.

Uploads need no key (embeddings run locally inside Brain) and go through the sandboxed
extractor (extraction.py). Every chat / upload / deletion is recorded for the admin panel.
"""
from __future__ import annotations

import time
from typing import Optional

import httpx
from fastapi import APIRouter, File, Form, Header, Request, UploadFile
from fastapi.responses import JSONResponse

from .. import analytics, auth, brain_client, limits, runtime
from ..auth import user_id_from_request
from ..config import settings
from ..extraction import ExtractionRejected
from ..schemas import (
    ChatRequest,
    DeleteAllRequest,
    DeleteRequest,
    SessionRequest,
    ThreadPatchRequest,
    public_providers,
)
from ..services import chat as chat_service
from ..services import documents as doc_service
from ..services import threads as thread_service

router = APIRouter()

HOSTED = "hosted"


# ── helpers ──────────────────────────────────────────────────────────────────


def _error(status_code: int, code: str, message: str, extra: dict | None = None) -> JSONResponse:
    payload = {"error": code, "message": message, "detail": message}
    if extra:
        payload.update(extra)
    return JSONResponse(status_code=status_code, content=payload)


def _brain_error(exc: brain_client.BrainError) -> JSONResponse:
    """Brain 4xx (bad key / bad request) → 400 with the provider's message; 5xx / unreachable →
    502 with a generic message (internal hostnames and stack details never reach the browser)."""
    if exc.status and 400 <= exc.status < 500:
        detail = exc.detail.replace("generation failed: ", "")[:300]
        return _error(400, "upstream_client_error", detail, {"upstream_status": exc.status})
    return _error(502, "upstream_error", "The answer service is temporarily unavailable. Please try again in a moment.")


async def _read_upload(file: UploadFile, max_mb: int) -> bytes | JSONResponse:
    """Read at most max_mb (+1 byte to detect overflow) — never buffer an unbounded body."""
    cap = max_mb * 1024 * 1024
    data = await file.read(cap + 1)
    if len(data) > cap:
        return _error(413, "file_too_large", f"Files can be at most {max_mb} MB.")
    return data


def _rate_limited(bucket: str, key: str, limit: int, window_s: float) -> Optional[JSONResponse]:
    if limits.allow(bucket, key, limit, window_s):
        return None
    return _error(429, "rate_limited", "Too many requests — please slow down and try again shortly.")


def _require_llm(provider: str, api_key: str, model: str) -> Optional[JSONResponse]:
    """Validate BYOK fields for an LLM call. Returns an error response or None."""
    provider = (provider or "").strip()
    cfg = runtime.current().byok
    if not cfg.enabled:
        return _error(403, "byok_disabled", "Bring-your-own-key mode is turned off right now.")
    if provider not in public_providers() or provider not in cfg.providers + (["ollama_local"] if settings.is_dev else []):
        return _error(400, "invalid_provider", f"Unsupported provider: {provider or '(none)'}.")
    if not (api_key or "").strip() and provider != "ollama_local":
        return _error(400, "byok_required", "An API key is required for this provider.")
    if not (model or "").strip():
        return _error(400, "model_required", "Select a model to continue.")
    return None


def _ctx(request: Request) -> tuple[str, str]:
    """(user_id, ip_hash) for the caller."""
    return user_id_from_request(request), auth.ip_hash(auth.client_ip(request))


def _hosted_quota(user_id: str, iph: str) -> Optional[JSONResponse]:
    h = runtime.current().hosted
    for bucket, key, limit, msg in (
        ("hosted_user", user_id, h.daily_per_user, f"You've used today's {h.daily_per_user} free questions. Add your own API key in Settings to keep going, or come back tomorrow."),
        ("hosted_ip", iph, h.daily_per_ip, "Today's free questions from your network are used up. Add your own API key in Settings to keep going."),
        ("hosted_global", "all", h.daily_global, "DocLens Free has hit today's capacity. Add your own API key in Settings to keep going, or try again tomorrow."),
    ):
        ok, _ = analytics.consume(bucket, key, limit)
        if not ok:
            return _error(429, "quota_exhausted", msg, {"quota": bucket})
    return None


# ── health, session, public config ───────────────────────────────────────────


@router.get("/health")
def health():
    return {"status": "ok", "service": "doclens"}


@router.post("/session")
def create_session(request: Request, body: SessionRequest | None = None):
    """Mint a signed anonymous session. An old unsigned browser token is upgraded in place
    (same user id) so existing documents and chats survive."""
    ip = auth.client_ip(request)
    err = _rate_limited("session", auth.ip_hash(ip), runtime.current().limits.sessions_per_hour_per_ip, 3600)
    if err is not None:
        return err
    if not auth.signing_enabled() and not settings.is_dev:
        return _error(503, "misconfigured", "Server misconfigured: SESSION_SECRET is not set.")
    legacy = auth.legacy_sub((body.legacy_token if body else "") or "")
    current = auth.verify(auth.bearer(request))  # a still-valid session is just refreshed
    token, sub = auth.mint(current or legacy or None)
    if not current:
        analytics.record("session", user=sub, ip=auth.ip_hash(ip), upgraded=bool(legacy))
    return {"token": token, "user_id": sub}


@router.get("/config")
def public_config(request: Request):
    """What the browser needs to render: is free mode on (and how much is left for this user),
    which BYOK providers/models to offer, upload limits, banner."""
    cfg = runtime.current()
    hosted = None
    if runtime.hosted_available(cfg):
        remaining = None
        try:
            uid = user_id_from_request(request)
            remaining = max(0, cfg.hosted.daily_per_user - analytics.used("hosted_user", uid))
        except Exception:  # noqa: BLE001 — no session yet
            pass
        hosted = {"label": cfg.hosted.label, "model": cfg.hosted.model, "daily_limit": cfg.hosted.daily_per_user, "remaining": remaining}
    return {
        "chat_enabled": cfg.service.chat_enabled,
        "banner": cfg.service.banner,
        "hosted": hosted,
        "byok": {
            "enabled": cfg.byok.enabled,
            "providers": [p for p in cfg.byok.providers if p in public_providers()],
            "suggested_models": cfg.byok.suggested_models,
        },
        "uploads": {
            "enabled": cfg.uploads.enabled,
            "max_mb": cfg.uploads.max_mb,
            "max_pages": cfg.uploads.max_pages,
            "max_docs": cfg.uploads.max_docs_per_user,
            "expire_hours": cfg.uploads.expire_hours,
        },
    }


@router.get("/models")
def list_models(request: Request, provider: str, x_provider_key: Optional[str] = Header(None)):
    user_id, iph = _ctx(request)
    err = _rate_limited("models", iph, 30, 600)
    if err is not None:
        return err
    suggested = runtime.current().byok.suggested_models
    if provider == "ollama_cloud":
        key = (x_provider_key or "").strip()
        if not key:
            return {"models": suggested.get("ollama_cloud", [])}
        try:
            resp = httpx.get("https://ollama.com/api/tags", headers={"Authorization": f"Bearer {key}"}, timeout=10)
            resp.raise_for_status()
            names = [m.get("name") or m.get("model") for m in resp.json().get("models", [])]
            models = sorted(n for n in names if n)
            return {"models": models or suggested.get("ollama_cloud", [])}
        except Exception:  # noqa: BLE001
            return {"models": suggested.get("ollama_cloud", [])}
    if provider in suggested:
        return {"models": suggested[provider]}
    return _error(400, "invalid_provider", f"Unknown provider: {provider[:30]!r}")


# ── chat ─────────────────────────────────────────────────────────────────────


@router.post("/chat")
def chat_endpoint(http_request: Request, request: ChatRequest):
    user_id, iph = _ctx(http_request)
    cfg = runtime.current()
    if not cfg.service.chat_enabled:
        return _error(503, "chat_disabled", cfg.service.banner or "DocLens is paused for maintenance. Please try again soon.")
    if not (request.query or "").strip():
        return _error(400, "empty_query", "Type a question first.")
    err = _rate_limited("chat", user_id, cfg.limits.chat_per_min_per_user, 60)
    if err is not None:
        return err

    mode = HOSTED if request.provider == HOSTED else "byok"
    if mode == HOSTED:
        if not runtime.hosted_available(cfg):
            return _error(403, "hosted_disabled", "Free mode is off right now. Add your own API key in Settings.")
        provider, api_key, model, fallback = "ollama_cloud", settings.hosted_ollama_api_key, cfg.hosted.model, cfg.hosted.fallback_model or None
    else:
        err = _require_llm(request.provider, request.api_key or "", request.model or "")
        if err is not None:
            return err
        provider, api_key, model, fallback = request.provider, (request.api_key or "").strip(), (request.model or "").strip(), None

    # quotas are spent only by requests that will actually run
    if mode == HOSTED:
        err = _hosted_quota(user_id, iph)
        if err is not None:
            analytics.record("quota", user=user_id, ip=iph, mode=mode)
            return err

    start = time.perf_counter()
    try:
        result = chat_service.run_chat(
            user_id=user_id,
            query=request.query,
            provider=provider,
            api_key=api_key,
            model=model,
            thread_id=request.thread_id,
            explicit_doc_ids=request.doc_ids,
            fallback_model=fallback,
        )
    except brain_client.BrainError as exc:
        analytics.record(
            "chat", user=user_id, ip=iph, mode=mode, provider=provider, model=model, query=request.query,
            error=f"{exc.status or 'unreachable'}", total_ms=round((time.perf_counter() - start) * 1000),
        )
        return _brain_error(exc)

    meta = result.setdefault("meta", {})
    meta["total_ms"] = round((time.perf_counter() - start) * 1000)
    meta["mode"] = mode
    if mode == HOSTED:
        meta["model_label"] = cfg.hosted.label
    analytics.record(
        "chat",
        user=user_id, ip=iph, mode=mode, provider=provider, model=meta.get("model") or model,
        thread_id=result.get("thread_id"), query=request.query, answer=result.get("answer"),
        grounded=result.get("grounded"), abstained=result.get("abstained"), blocked=result.get("blocked"),
        citations=len(result.get("citations") or []), guardrails=meta.get("guardrails") or [],
        total_ms=meta["total_ms"], retrieve_ms=meta.get("retrieve_ms"), generate_ms=meta.get("generate_ms"),
        verify_ms=meta.get("verify_ms"), rewrite_ms=meta.get("rewrite_ms"), top_score=meta.get("top_score"),
        retrieved=meta.get("retrieved_count"), answer_words=len((result.get("answer") or "").split()),
    )
    if mode != HOSTED:
        meta.pop("model_label", None)
    return result


# ── uploads (per-chat paperclip + global resources) ──────────────────────────


async def _upload(request: Request, file: UploadFile, scope: str, thread_id: Optional[str]) -> dict | JSONResponse:
    user_id, iph = _ctx(request)
    ucfg = runtime.current().uploads
    filename = (file.filename or "document").replace("\\", "/").split("/")[-1][:200] or "document"

    def reject(code: str, message: str, status: int) -> JSONResponse:
        analytics.record("upload_rejected", user=user_id, ip=iph, filename=filename, reason=code, scope=scope)
        return _error(status, code, message)

    if not ucfg.enabled:
        return _error(503, "uploads_disabled", "Uploads are paused right now. Please try again later.")
    err = _rate_limited("upload", user_id, ucfg.per_10min_per_user, 600)
    if err is not None:
        return err
    content = await _read_upload(file, ucfg.max_mb)
    if isinstance(content, JSONResponse):
        return reject("file_too_large", f"Files can be at most {ucfg.max_mb} MB.", 413)
    ok, _ = analytics.consume("uploads_user", user_id, ucfg.daily_per_user)
    if not ok:
        return _error(429, "upload_quota", f"You've reached today's limit of {ucfg.daily_per_user} uploads.")

    created_thread = None
    if scope == "thread" and not thread_id:
        # A paperclip upload in a brand-new chat creates the chat so the doc has a home.
        created_thread = thread_service.create_thread(user_id, title=filename)
        thread_id = created_thread["id"]
    elif scope == "thread" and not thread_service.get_thread_raw(user_id, thread_id):
        return _error(404, "not_found", "Chat not found.")

    start = time.perf_counter()
    try:
        doc = await _in_thread(
            doc_service.ingest_document,
            user_id=user_id, file_bytes=content, filename=filename,
            content_type=(file.content_type or "")[:100], scope=scope, thread_id=thread_id,
        )
    except (ExtractionRejected, brain_client.BrainError) as exc:
        if created_thread:  # a failed first upload leaves no ghost chat
            thread_service.delete_thread(user_id, thread_id)
        if isinstance(exc, ExtractionRejected):
            return reject(exc.code, exc.message, exc.status)
        analytics.record("upload_rejected", user=user_id, ip=iph, filename=filename, reason="brain_error", scope=scope)
        return _brain_error(exc)

    ms = round((time.perf_counter() - start) * 1000)
    if not doc.get("duplicate"):
        stats = doc.get("stats") or {}
        analytics.record(
            "upload", user=user_id, ip=iph, filename=filename, scope=scope, size_bytes=len(content),
            pages=doc.get("pages"), chunks=doc.get("chunk_count"), warnings=doc.get("warnings") or [],
            duration_ms=ms, tables=stats.get("tables"), images=stats.get("images"),
            multi_column_pages=stats.get("multi_column_pages"),
        )
    return {
        "status": "success",
        "doc_id": doc["doc_id"],
        "filename": doc["filename"],
        "chunk_count": doc["chunk_count"],
        "pages": doc.get("pages"),
        "duplicate": doc.get("duplicate", False),
        "warnings": doc.get("warnings", []),
        "expires_at": doc.get("expires_at"),
        "thread_id": thread_id if scope == "thread" else None,
        "meta": {"ingest_ms": ms},
    }


async def _in_thread(fn, **kw):
    # extraction + Brain ingest block for seconds: keep them off the event loop
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(lambda: fn(**kw))


@router.post("/ingest")
async def ingest_endpoint(request: Request, file: UploadFile = File(...), thread_id: Optional[str] = Form(None)):
    return await _upload(request, file, "thread", (thread_id or "")[:64] or None)


@router.post("/resources")
async def upload_resource(request: Request, file: UploadFile = File(...)):
    return await _upload(request, file, "global", None)


@router.get("/documents")
def list_documents_endpoint(request: Request, thread_id: Optional[str] = None):
    user_id = user_id_from_request(request)
    # No thread context (a draft chat) has no attachments yet.
    docs = doc_service.list_documents(user_id, thread_id=thread_id) if thread_id else []
    return {"documents": docs}


@router.post("/delete")
def delete_endpoint(http_request: Request, request: DeleteRequest):
    user_id, iph = _ctx(http_request)
    chunks = doc_service.delete_document(user_id, request.doc_id)
    if chunks is not None:
        analytics.record("delete", user=user_id, ip=iph, reason="user", docs=1, chunks=chunks)
    return {"status": "success", "result": {"deleted": 0 if chunks is None else 1}}


@router.post("/delete_all")
def delete_all_endpoint(http_request: Request, _request: DeleteAllRequest | None = None):
    user_id, iph = _ctx(http_request)
    # Wipe vectors + registry + all chat sessions/messages for a clean reset.
    docs, chunks = doc_service.delete_all(user_id)
    from .. import db

    db.threads().delete_many({"user_id": user_id})
    db.messages().delete_many({"user_id": user_id})
    analytics.record("delete", user=user_id, ip=iph, reason="reset", docs=docs, chunks=chunks)
    return {"status": "success", "result": {"deleted_documents": docs}}


@router.get("/resources")
def list_resources(request: Request):
    user_id = user_id_from_request(request)
    return {"documents": doc_service.list_documents(user_id, scope="global")}


@router.delete("/resources/{doc_id}")
def delete_resource(doc_id: str, request: Request):
    user_id, iph = _ctx(request)
    chunks = doc_service.delete_document(user_id, doc_id[:64])
    if chunks is not None:
        analytics.record("delete", user=user_id, ip=iph, reason="user", docs=1, chunks=chunks)
    return {"status": "deleted"}


# ── chat sessions (threads) ──────────────────────────────────────────────────


@router.get("/threads")
def list_threads_endpoint(request: Request):
    return {"threads": thread_service.list_threads(user_id_from_request(request))}


@router.get("/threads/{thread_id}")
def get_thread_endpoint(thread_id: str, request: Request):
    user_id = user_id_from_request(request)
    thread = thread_service.get_thread_raw(user_id, thread_id)
    if not thread:
        return _error(404, "not_found", "Chat not found.")
    return {
        "id": thread["_id"],
        "title": thread.get("title"),
        "messages": thread_service.thread_messages(user_id, thread_id),
        "documents": doc_service.list_documents(user_id, thread_id=thread_id),
    }


@router.patch("/threads/{thread_id}")
def patch_thread_endpoint(thread_id: str, request: ThreadPatchRequest, http_request: Request):
    updated = thread_service.rename_thread(user_id_from_request(http_request), thread_id, request.title or "")
    if not updated:
        return _error(404, "not_found", "Chat not found.")
    return updated


@router.delete("/threads/{thread_id}")
def delete_thread_endpoint(thread_id: str, request: Request):
    user_id, iph = _ctx(request)
    # Remove this chat's private documents (and their vectors), then the chat itself.
    docs, chunks = doc_service.delete_thread_documents(user_id, thread_id)
    thread_service.delete_thread(user_id, thread_id)
    if docs:
        analytics.record("delete", user=user_id, ip=iph, reason="chat_deleted", docs=docs, chunks=chunks)
    return {"status": "deleted"}
