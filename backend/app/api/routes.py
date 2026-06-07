"""DocLens HTTP API.

A thin orchestration + state layer: validates requests, resolves the user, owns
chat-session/document state in Mongo, and delegates all RAG/LLM work to Brain.
BYOK is enforced for anything that calls the LLM (chat) — the user's key is
required, with no fallback to Brain's own credentials. Uploads need no key
(embeddings run locally inside Brain).
"""
from __future__ import annotations

import time
from typing import Optional

import httpx
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from .. import brain_client
from ..auth import user_id_from_request
from ..schemas import (
    ChatRequest,
    DeleteAllRequest,
    DeleteRequest,
    ThreadPatchRequest,
    VALID_PROVIDERS,
)
from ..services import chat as chat_service
from ..services import documents as doc_service
from ..services import threads as thread_service

router = APIRouter()

_OPENAI_MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1", "o4-mini"]
_ANTHROPIC_MODELS = ["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5-20251001"]
_OLLAMA_CLOUD_FALLBACK = ["gpt-oss:120b", "gpt-oss:20b"]

_SUPPORTED_UPLOAD_HINT = "Supported types: PDF, DOCX, Markdown (.md), or plain text."


# ── helpers ──────────────────────────────────────────────────────────────────


def _error(status_code: int, code: str, message: str, extra: dict | None = None) -> JSONResponse:
    payload = {"error": code, "message": message, "detail": message}
    if extra:
        payload.update(extra)
    return JSONResponse(status_code=status_code, content=payload)


def _brain_error(exc: brain_client.BrainError) -> JSONResponse:
    """Brain 4xx (bad key / bad request) → 400 to the browser; 5xx / unreachable → 502."""
    if exc.status and 400 <= exc.status < 500:
        return _error(400, "upstream_client_error", exc.detail, {"upstream_status": exc.status})
    return _error(502, "upstream_error", exc.detail, {"upstream_status": exc.status})


def _require_llm(provider: str, api_key: str, model: str) -> Optional[JSONResponse]:
    """Validate BYOK fields for an LLM call. Returns an error response or None."""
    provider = (provider or "").strip()
    if provider not in VALID_PROVIDERS:
        return _error(400, "invalid_provider", f"Unsupported provider: {provider or '(none)'}.")
    if not (api_key or "").strip() and provider != "ollama_local":
        return _error(400, "byok_required", "An API key is required — DocLens uses your own key.")
    if not (model or "").strip():
        return _error(400, "model_required", "Select a model to continue.")
    return None


# ── health & models ──────────────────────────────────────────────────────────


@router.get("/health")
def health():
    return {"status": "ok", "service": "doclens", "brain": brain_client.settings.brain_base_url}


@router.get("/models")
def list_models(provider: str, api_key: str = ""):
    if provider == "openai":
        return {"models": _OPENAI_MODELS}
    if provider == "anthropic":
        return {"models": _ANTHROPIC_MODELS}
    if provider == "ollama_cloud":
        key = (api_key or "").strip()
        if not key:
            return {"models": _OLLAMA_CLOUD_FALLBACK}
        try:
            resp = httpx.get(
                "https://ollama.com/api/tags",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10,
            )
            resp.raise_for_status()
            names = [m.get("name") or m.get("model") for m in resp.json().get("models", [])]
            models = sorted(n for n in names if n)
            return {"models": models or _OLLAMA_CLOUD_FALLBACK}
        except Exception:  # noqa: BLE001
            return {"models": _OLLAMA_CLOUD_FALLBACK}
    if provider == "ollama_local":
        return {"models": []}
    return _error(400, "invalid_provider", f"Unknown provider: {provider!r}")


# ── chat ─────────────────────────────────────────────────────────────────────


@router.post("/chat")
def chat_endpoint(http_request: Request, request: ChatRequest):
    user_id = user_id_from_request(http_request, request.user_id)
    err = _require_llm(request.provider, request.api_key or "", request.model or "")
    if err is not None:
        return err

    start = time.perf_counter()
    try:
        result = chat_service.run_chat(
            user_id=user_id,
            query=request.query,
            provider=request.provider,
            api_key=(request.api_key or "").strip(),
            model=(request.model or "").strip(),
            thread_id=request.thread_id,
            explicit_doc_ids=request.doc_ids,
        )
    except brain_client.BrainError as exc:
        return _brain_error(exc)

    result.setdefault("meta", {})["total_ms"] = round((time.perf_counter() - start) * 1000)
    return result


# ── per-chat document upload (paperclip) ─────────────────────────────────────


@router.post("/ingest")
def ingest_endpoint(
    request: Request,
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    api_key: str = Form(""),  # accepted but unused — ingestion needs no LLM key
    thread_id: Optional[str] = Form(None),
):
    resolved_user_id = user_id_from_request(request, user_id)
    content = file.file.read()
    if not content:
        return _error(400, "empty_file", "The uploaded file is empty.")

    # A paperclip upload in a brand-new chat creates the chat so the doc has a home.
    created_thread = None
    if not thread_id:
        created_thread = thread_service.create_thread(resolved_user_id, title=file.filename or "New chat")
        thread_id = created_thread["id"]

    start = time.perf_counter()
    try:
        doc = doc_service.ingest_document(
            user_id=resolved_user_id,
            file_bytes=content,
            filename=file.filename or "document",
            content_type=file.content_type or "",
            scope="thread",
            thread_id=thread_id,
        )
    except brain_client.BrainError as exc:
        # Roll back an auto-created empty thread so a failed first upload leaves no ghost chat.
        if created_thread:
            thread_service.delete_thread(resolved_user_id, thread_id)
        return _brain_error(exc)

    return {
        "status": "success",
        "doc_id": doc["doc_id"],
        "filename": doc["filename"],
        "chunk_count": doc["chunk_count"],
        "thread_id": thread_id,
        "meta": {"ingest_ms": round((time.perf_counter() - start) * 1000)},
    }


@router.get("/documents")
def list_documents_endpoint(request: Request, user_id: Optional[str] = None, thread_id: Optional[str] = None):
    resolved_user_id = user_id_from_request(request, user_id)
    if thread_id:
        docs = doc_service.list_documents(resolved_user_id, thread_id=thread_id)
    else:
        # No thread context (a draft chat) has no attachments yet.
        docs = []
    return {"documents": docs}


@router.post("/delete")
def delete_endpoint(http_request: Request, request: DeleteRequest):
    user_id = user_id_from_request(http_request)
    removed = doc_service.delete_document(user_id, request.doc_id)
    return {"status": "success", "result": {"deleted": 1 if removed else 0}}


@router.post("/delete_all")
def delete_all_endpoint(http_request: Request, _request: DeleteAllRequest):
    user_id = user_id_from_request(http_request)
    # Wipe vectors + registry + all chat sessions/messages for a clean reset.
    count = doc_service.delete_all(user_id)
    from .. import db

    db.threads().delete_many({"user_id": user_id})
    db.messages().delete_many({"user_id": user_id})
    return {"status": "success", "result": {"deleted_documents": count}}


# ── global resources (left panel) ────────────────────────────────────────────


@router.post("/resources")
def upload_resource(request: Request, file: UploadFile = File(...), user_id: Optional[str] = Form(None)):
    resolved_user_id = user_id_from_request(request, user_id)
    content = file.file.read()
    if not content:
        return _error(400, "empty_file", "The uploaded file is empty.")
    try:
        doc = doc_service.ingest_document(
            user_id=resolved_user_id,
            file_bytes=content,
            filename=file.filename or "document",
            content_type=file.content_type or "",
            scope="global",
        )
    except brain_client.BrainError as exc:
        return _brain_error(exc)
    return {"status": "ok", "doc_id": doc["doc_id"], "filename": doc["filename"], "chunk_count": doc["chunk_count"]}


@router.get("/resources")
def list_resources(request: Request, user_id: Optional[str] = None):
    resolved_user_id = user_id_from_request(request, user_id)
    return {"documents": doc_service.list_documents(resolved_user_id, scope="global")}


@router.delete("/resources/{doc_id}")
def delete_resource(doc_id: str, request: Request, user_id: Optional[str] = None):
    resolved_user_id = user_id_from_request(request, user_id)
    doc_service.delete_document(resolved_user_id, doc_id)
    return {"status": "deleted"}


# ── chat sessions (threads) ──────────────────────────────────────────────────


@router.get("/threads")
def list_threads_endpoint(request: Request, user_id: Optional[str] = None):
    resolved_user_id = user_id_from_request(request, user_id)
    return {"threads": thread_service.list_threads(resolved_user_id)}


@router.get("/threads/{thread_id}")
def get_thread_endpoint(thread_id: str, request: Request, user_id: Optional[str] = None):
    resolved_user_id = user_id_from_request(request, user_id)
    thread = thread_service.get_thread_raw(resolved_user_id, thread_id)
    if not thread:
        return _error(404, "not_found", "Chat not found.")
    return {
        "id": thread["_id"],
        "title": thread.get("title"),
        "messages": thread_service.thread_messages(resolved_user_id, thread_id),
        "documents": doc_service.list_documents(resolved_user_id, thread_id=thread_id),
    }


@router.patch("/threads/{thread_id}")
def patch_thread_endpoint(thread_id: str, request: ThreadPatchRequest, http_request: Request, user_id: Optional[str] = None):
    resolved_user_id = user_id_from_request(http_request, user_id)
    updated = thread_service.rename_thread(resolved_user_id, thread_id, request.title or "")
    if not updated:
        return _error(404, "not_found", "Chat not found.")
    return updated


@router.delete("/threads/{thread_id}")
def delete_thread_endpoint(thread_id: str, request: Request, user_id: Optional[str] = None):
    resolved_user_id = user_id_from_request(request, user_id)
    # Remove this chat's private documents (and their vectors), then the chat itself.
    doc_service.delete_thread_documents(resolved_user_id, thread_id)
    thread_service.delete_thread(resolved_user_id, thread_id)
    return {"status": "deleted"}
