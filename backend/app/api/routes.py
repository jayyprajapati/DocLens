import json
import os
import time

import requests
from typing import List, Literal, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
import base64

from app.config import CORTEX_BASE_URL
from app.services.delete_service import run_delete, run_delete_all
from app.services.ingest_service import run_ingest
from app.services.query_service import run_query
from services.rag_client import (
    chat as rag_chat,
    delete_thread as rag_delete_thread,
    get_thread as rag_get_thread,
    list_threads as rag_list_threads,
    patch_thread as rag_patch_thread,
    stream_chat as rag_stream_chat,
    cortex,
    WORKSPACE_ID as CORTEX_WORKSPACE_ID,
)


router = APIRouter()

VALID_PROVIDERS = {"openai", "ollama_cloud"}


class QueryRequest(BaseModel):
    query: str
    user_id: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    provider: Literal["openai", "ollama_cloud"] = "openai"
    doc_ids: Optional[List[str]] = None


class ChatRequest(BaseModel):
    query: str
    user_id: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    provider: Literal["openai", "ollama_cloud"] = "openai"
    thread_id: Optional[str] = None
    doc_ids: Optional[List[str]] = None


class ThreadPatchRequest(BaseModel):
    title: Optional[str] = None


class DeleteRequest(BaseModel):
    doc_id: str = Field(min_length=1)


class DeleteAllRequest(BaseModel):
    pass


def _decode_b64url(value):
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("utf-8"))


def _user_id_from_request(request: Request, fallback=None):
    fallback = (fallback or "").strip()
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    if token:
        try:
            parts = token.split(".")
            if len(parts) >= 2:
                payload = json.loads(_decode_b64url(parts[1]).decode("utf-8"))
                sub = str(payload.get("sub") or "").strip()
                if sub:
                    return sub
        except Exception:
            pass

    if fallback:
        return fallback

    raise HTTPException(status_code=401, detail="Authorization bearer token with sub claim is required")


def _llm_options(payload):
    api_key = (payload.api_key or "").strip()
    model = (payload.model or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required.")
    if not model:
        raise HTTPException(status_code=400, detail="Model is required.")
    return {
        "provider": payload.provider,
        "api_key": api_key,
        "model": model,
    }


def _extract_doc_id(ingest_result):
    if not isinstance(ingest_result, dict):
        return None

    candidates = [
        ingest_result.get("doc_id"),
        ingest_result.get("document_id"),
        ingest_result.get("id"),
    ]

    nested = ingest_result.get("result")
    if isinstance(nested, dict):
        candidates += [nested.get("doc_id"), nested.get("document_id"), nested.get("id")]

    for c in candidates:
        if isinstance(c, str) and c.strip():
            return c.strip()

    return None


def _safe_duration(value, default_value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return round(float(default_value), 4)
    return round(parsed, 4) if parsed >= 0 else round(float(default_value), 4)


def _build_meta(raw_meta, elapsed_ms):
    if not isinstance(raw_meta, dict):
        raw_meta = {}
    return {
        "retrieval_time": _safe_duration(raw_meta.get("retrieval_time"), elapsed_ms),
        "generation_time": _safe_duration(raw_meta.get("generation_time"), 0),
    }


def _error_response(status_code, error_code, message, extra=None):
    payload = {"error": error_code, "message": message, "detail": message}
    if isinstance(extra, dict):
        payload.update(extra)
    return JSONResponse(status_code=status_code, content=payload)


def _upstream_detail(exc):
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.text
    return str(exc)


def _handle_upstream_error(exc, action):
    """
    Return the right HTTP status to the browser based on what Cortex returned.
    - Cortex 4xx (bad key, bad provider, bad request) → 400 to browser (client error)
    - Cortex 5xx or connectivity failure → 502 to browser (gateway error)
    """
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        upstream_status = exc.response.status_code
        if 400 <= upstream_status < 500:
            return _error_response(
                400,
                "upstream_client_error",
                f"{action} failed: check your API key and provider selection.",
                {"upstream_detail": exc.response.text},
            )
    return _error_response(
        502,
        "upstream_error",
        f"{action} failed: upstream service error.",
        {"upstream_detail": _upstream_detail(exc)},
    )


def _sse_event(event_type, data):
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _latest_thread_id(user_id):
    data = rag_list_threads(user_id=user_id, app_name="doclens", base_url=CORTEX_BASE_URL, timeout=10)
    threads = data.get("threads", []) if isinstance(data, dict) else []
    if not threads:
        return None
    return threads[0].get("id")


@router.get("/documents")
async def list_documents_endpoint(request: Request, user_id: Optional[str] = None, thread_id: Optional[str] = None):
    resolved_user_id = _user_id_from_request(request, user_id)
    try:
        if thread_id:
            docs = await cortex.list_documents(
                user_id=resolved_user_id,
                workspace_id=CORTEX_WORKSPACE_ID,
                scope_kind="thread",
                scope_id=thread_id,
            )
        else:
            docs = await cortex.list_documents(
                user_id=resolved_user_id,
                workspace_id=CORTEX_WORKSPACE_ID,
                scope_kind="workspace",
            )
    except Exception as exc:
        return _error_response(502, "upstream_error", "List documents failed: could not reach Cortex.",
                               {"upstream_detail": str(exc)})

    for d in docs:
        if not d.get("filename"):
            d["filename"] = f"doc-{(d.get('doc_id') or d.get('id') or 'unknown')[:8]}"
    return {"documents": docs}


_OPENAI_MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1", "o4-mini"]
_OLLAMA_CLOUD_FALLBACK = ["gpt-oss:120b"]


@router.get("/models")
def list_models_endpoint(provider: str, api_key: str = ""):
    if provider == "openai":
        return {"models": _OPENAI_MODELS}

    if provider == "ollama_cloud":
        if not api_key.strip():
            return {"models": _OLLAMA_CLOUD_FALLBACK}
        try:
            resp = requests.get(
                "https://ollama.com/api/tags",
                headers={"Authorization": f"Bearer {api_key.strip()}"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            names = [
                m.get("name") or m.get("model")
                for m in data.get("models", [])
            ]
            models = sorted(n for n in names if n)
            return {"models": models or _OLLAMA_CLOUD_FALLBACK}
        except Exception:
            return {"models": _OLLAMA_CLOUD_FALLBACK}

    return _error_response(400, "invalid_provider", f"Unknown provider: {provider!r}")


@router.post("/query")
def query_endpoint(http_request: Request, request: QueryRequest):
    user_id = _user_id_from_request(http_request, request.user_id)

    llm = _llm_options(request)

    final_doc_ids = request.doc_ids

    start = time.perf_counter()
    try:
        result = run_query(query=request.query, user_id=user_id, llm=llm, doc_ids=final_doc_ids)
    except requests.HTTPError as exc:
        return _handle_upstream_error(exc, "Query")
    except requests.RequestException as exc:
        return _error_response(502, "upstream_error", "Query failed: could not reach Cortex.",
                               {"upstream_detail": str(exc)})

    elapsed_ms = (time.perf_counter() - start) * 1000
    payload = dict(result) if isinstance(result, dict) else {"result": result}
    payload["meta"] = _build_meta(payload.get("meta"), elapsed_ms)
    return payload


@router.post("/chat")
def chat_endpoint(http_request: Request, request: ChatRequest):
    """Multi-turn chat with persisted thread history (handled by Cortex)."""
    user_id = _user_id_from_request(http_request, request.user_id)

    explicit_doc_ids = request.doc_ids

    llm = _llm_options(request)

    start = time.perf_counter()
    try:
        result = rag_chat(
            query=request.query,
            user_id=user_id,
            thread_id=request.thread_id,
            doc_ids=explicit_doc_ids,
            llm=llm,
            base_url=CORTEX_BASE_URL,
        )
    except requests.HTTPError as exc:
        return _handle_upstream_error(exc, "Chat")
    except requests.RequestException as exc:
        return _error_response(
            502, "upstream_error",
            "Chat failed: could not reach Cortex.",
            {"upstream_detail": str(exc)},
        )

    elapsed_ms = (time.perf_counter() - start) * 1000
    payload = dict(result) if isinstance(result, dict) else {"result": result}
    payload["meta"] = _build_meta(payload.get("meta"), elapsed_ms)
    return payload


@router.post("/chat/stream")
def chat_stream_endpoint(http_request: Request, request: ChatRequest):
    """Proxy Cortex /chat SSE and append DocLens thread metadata at the end."""
    user_id = _user_id_from_request(http_request, request.user_id)

    explicit_doc_ids = request.doc_ids

    llm = _llm_options(request)

    try:
        upstream = rag_stream_chat(
            query=request.query,
            user_id=user_id,
            thread_id=request.thread_id,
            doc_ids=explicit_doc_ids,
            llm=llm,
            base_url=CORTEX_BASE_URL,
        )
    except requests.HTTPError as exc:
        return _handle_upstream_error(exc, "Chat")
    except requests.RequestException as exc:
        return _error_response(
            502, "upstream_error",
            "Chat failed: could not reach Cortex.",
            {"upstream_detail": str(exc)},
        )

    def _proxy():
        try:
            for chunk in upstream.iter_content(chunk_size=1024):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

        thread_id = request.thread_id
        if not thread_id:
            try:
                thread_id = _latest_thread_id(user_id)
            except requests.RequestException:
                thread_id = None

        if thread_id:
            yield _sse_event("thread", {"thread_id": thread_id}).encode("utf-8")

    return StreamingResponse(
        _proxy(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/threads")
def list_threads_endpoint(request: Request, user_id: Optional[str] = None):
    user_id = _user_id_from_request(request, user_id)
    try:
        return rag_list_threads(user_id=user_id, app_name="doclens", base_url=CORTEX_BASE_URL)
    except requests.HTTPError as exc:
        return _handle_upstream_error(exc, "List threads")
    except requests.RequestException as exc:
        return _error_response(
            502, "upstream_error",
            "List threads failed: could not reach Cortex.",
            {"upstream_detail": str(exc)},
        )


@router.get("/threads/{thread_id}")
def get_thread_endpoint(thread_id: str, request: Request, user_id: Optional[str] = None):
    user_id = _user_id_from_request(request, user_id)
    try:
        return rag_get_thread(thread_id=thread_id, user_id=user_id, base_url=CORTEX_BASE_URL)
    except requests.HTTPError as exc:
        return _handle_upstream_error(exc, "Get thread")
    except requests.RequestException as exc:
        return _error_response(
            502, "upstream_error",
            "Get thread failed: could not reach Cortex.",
            {"upstream_detail": str(exc)},
        )


@router.delete("/threads/{thread_id}")
def delete_thread_endpoint(thread_id: str, request: Request, user_id: Optional[str] = None):
    user_id = _user_id_from_request(request, user_id)
    try:
        return rag_delete_thread(thread_id=thread_id, user_id=user_id, base_url=CORTEX_BASE_URL)
    except requests.HTTPError as exc:
        return _handle_upstream_error(exc, "Delete thread")
    except requests.RequestException as exc:
        return _error_response(
            502, "upstream_error",
            "Delete thread failed: could not reach Cortex.",
            {"upstream_detail": str(exc)},
        )


@router.patch("/threads/{thread_id}")
def patch_thread_endpoint(thread_id: str, request: ThreadPatchRequest, http_request: Request, user_id: Optional[str] = None):
    user_id = _user_id_from_request(http_request, user_id)
    try:
        return rag_patch_thread(
            thread_id=thread_id,
            user_id=user_id,
            title=request.title,
            base_url=CORTEX_BASE_URL,
        )
    except requests.HTTPError as exc:
        return _handle_upstream_error(exc, "Update thread")
    except requests.RequestException as exc:
        return _error_response(
            502, "upstream_error",
            "Update thread failed: could not reach Cortex.",
            {"upstream_detail": str(exc)},
        )


@router.post("/ingest")
async def ingest_endpoint(
    request: Request,
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    api_key: str = Form(""),
    thread_id: Optional[str] = Form(None),
):
    user_id = _user_id_from_request(request, user_id)
    if not api_key.strip():
        return _error_response(400, "byok_required", "API key is required to upload documents.")

    start = time.perf_counter()

    try:
        content = await file.read()

        scope_kind = "thread" if thread_id else "workspace"
        scope_id = thread_id if thread_id else CORTEX_WORKSPACE_ID

        doc_id = await cortex.ingest(
            file_bytes=content,
            filename=file.filename,
            user_id=user_id,
            workspace_id=CORTEX_WORKSPACE_ID,
            scope_kind=scope_kind,
            scope_id=scope_id,
        )

        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "status": "success",
            "doc_id": doc_id,
            "meta": _build_meta({}, elapsed_ms),
        }

    except Exception as exc:
        return _error_response(502, "upstream_error", "Ingest failed: could not reach Cortex.",
                               {"upstream_detail": str(exc)})
    finally:
        await file.close()


@router.post("/resources")
async def upload_resource(
    request: Request,
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
):
    resolved_user_id = _user_id_from_request(request, user_id)
    try:
        content = await file.read()
        doc_id = await cortex.ingest(
            file_bytes=content,
            filename=file.filename,
            user_id=resolved_user_id,
            workspace_id=CORTEX_WORKSPACE_ID,
            scope_kind="workspace",
            scope_id=CORTEX_WORKSPACE_ID,
        )
        return {"status": "ok", "doc_id": doc_id, "filename": file.filename}
    except Exception as exc:
        return _error_response(502, "upstream_error", "Resource upload failed: could not reach Cortex.",
                               {"upstream_detail": str(exc)})
    finally:
        await file.close()


@router.get("/resources")
async def list_resources(request: Request, user_id: Optional[str] = None):
    resolved_user_id = _user_id_from_request(request, user_id)
    try:
        docs = await cortex.list_documents(
            user_id=resolved_user_id,
            workspace_id=CORTEX_WORKSPACE_ID,
            scope_kind="workspace",
        )
        return {"documents": docs}
    except Exception as exc:
        return _error_response(502, "upstream_error", "List resources failed: could not reach Cortex.",
                               {"upstream_detail": str(exc)})


@router.delete("/resources/{doc_id}")
async def delete_resource(doc_id: str, request: Request, user_id: Optional[str] = None):
    resolved_user_id = _user_id_from_request(request, user_id)
    try:
        await cortex.delete_document(user_id=resolved_user_id, document_id=doc_id)
        return {"status": "deleted"}
    except Exception as exc:
        return _error_response(502, "upstream_error", "Delete resource failed: could not reach Cortex.",
                               {"upstream_detail": str(exc)})


@router.post("/delete")
def delete_endpoint(http_request: Request, request: DeleteRequest):
    user_id = _user_id_from_request(http_request)
    start = time.perf_counter()
    try:
        result = run_delete(user_id=user_id, doc_id=request.doc_id, app_name="doclens")
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return {"status": "success", "result": {"deleted_points": 0}, "meta": _build_meta({}, elapsed_ms)}
        return _handle_upstream_error(exc, "Delete")
    except requests.RequestException as exc:
        return _error_response(502, "upstream_error", "Delete failed: could not reach Cortex.",
                               {"upstream_detail": str(exc)})
    elapsed_ms = (time.perf_counter() - start) * 1000
    return {"status": "success", "result": result, "meta": _build_meta({}, elapsed_ms)}


@router.post("/delete_all")
def delete_all_endpoint(http_request: Request, _request: DeleteAllRequest):
    user_id = _user_id_from_request(http_request)
    start = time.perf_counter()
    try:
        result = run_delete_all(user_id=user_id, app_name="doclens")
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"status": "success", "result": result, "meta": _build_meta({}, elapsed_ms)}
    except requests.HTTPError as exc:
        return _handle_upstream_error(exc, "Delete all")
    except requests.RequestException as exc:
        return _error_response(502, "upstream_error", "Delete all failed: could not reach Cortex.",
                               {"upstream_detail": str(exc)})
