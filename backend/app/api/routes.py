import os
import tempfile
import time

import requests
from typing import List, Literal, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.services.delete_service import run_delete, run_delete_all
from app.services.document_registry import (
    list_documents,
    register_document,
    remove_all_documents,
    remove_document,
)
from app.services.ingest_service import run_ingest
from app.services.query_service import run_query


router = APIRouter()

VALID_PROVIDERS = {"openai", "ollama_cloud"}


class QueryRequest(BaseModel):
    query: str
    user_id: str
    api_key: str = Field(min_length=1)
    model: str = Field(min_length=1)
    provider: Literal["openai", "ollama_cloud"] = "openai"
    doc_ids: Optional[List[str]] = None


class DeleteRequest(BaseModel):
    user_id: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)


class DeleteAllRequest(BaseModel):
    user_id: str = Field(min_length=1)


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


@router.get("/documents")
def list_documents_endpoint(user_id: str):
    if not user_id.strip():
        return _error_response(400, "invalid_user", "user_id is required")
    docs = list_documents(user_id.strip())
    for d in docs:
        if not d.get("filename"):
            d["filename"] = f"doc-{d['doc_id'][:8]}"
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
def query_endpoint(request: QueryRequest):
    # Auto-scope to the user's only document if they have exactly one
    user_docs = list_documents(request.user_id)
    auto_doc_ids = [user_docs[0]["doc_id"]] if len(user_docs) == 1 else None

    llm = {
        "provider": request.provider,
        "api_key": request.api_key,
        "model": request.model,
    }

    final_doc_ids = request.doc_ids or auto_doc_ids

    start = time.perf_counter()
    try:
        result = run_query(query=request.query, user_id=request.user_id, llm=llm, doc_ids=final_doc_ids)
    except requests.HTTPError as exc:
        return _handle_upstream_error(exc, "Query")
    except requests.RequestException as exc:
        return _error_response(502, "upstream_error", "Query failed: could not reach Cortex.",
                               {"upstream_detail": str(exc)})

    elapsed_ms = (time.perf_counter() - start) * 1000
    payload = dict(result) if isinstance(result, dict) else {"result": result}
    payload["meta"] = _build_meta(payload.get("meta"), elapsed_ms)
    return payload


@router.post("/ingest")
async def ingest_endpoint(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    api_key: str = Form(...),
):
    if not api_key.strip():
        return _error_response(400, "byok_required", "API key is required to upload documents.")

    temp_path = None
    start = time.perf_counter()

    try:
        suffix = os.path.splitext(file.filename or "")[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            temp_path = tmp.name
            tmp.write(await file.read())

        result = run_ingest(file_path=temp_path, user_id=user_id, app_name="doclens")

        doc_id = _extract_doc_id(result)
        if not doc_id:
            return _error_response(500, "missing_doc_id", "Ingest response missing doc_id.")

        register_document(user_id=user_id, doc_id=doc_id, filename=file.filename)

        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "status": "success",
            "doc_id": doc_id,
            "meta": _build_meta({}, elapsed_ms),
        }

    except requests.HTTPError as exc:
        return _handle_upstream_error(exc, "Ingest")
    except requests.RequestException as exc:
        return _error_response(502, "upstream_error", "Ingest failed: could not reach Cortex.",
                               {"upstream_detail": str(exc)})
    finally:
        await file.close()
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


@router.post("/delete")
def delete_endpoint(request: DeleteRequest):
    start = time.perf_counter()
    try:
        result = run_delete(user_id=request.user_id, doc_id=request.doc_id, app_name="doclens")
        remove_document(user_id=request.user_id, doc_id=request.doc_id)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"status": "success", "result": result, "meta": _build_meta({}, elapsed_ms)}
    except requests.HTTPError as exc:
        return _handle_upstream_error(exc, "Delete")
    except requests.RequestException as exc:
        return _error_response(502, "upstream_error", "Delete failed: could not reach Cortex.",
                               {"upstream_detail": str(exc)})


@router.post("/delete_all")
def delete_all_endpoint(request: DeleteAllRequest):
    start = time.perf_counter()
    try:
        result = run_delete_all(user_id=request.user_id, app_name="doclens")
        remove_all_documents(user_id=request.user_id)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"status": "success", "result": result, "meta": _build_meta({}, elapsed_ms)}
    except requests.HTTPError as exc:
        return _handle_upstream_error(exc, "Delete all")
    except requests.RequestException as exc:
        return _error_response(502, "upstream_error", "Delete all failed: could not reach Cortex.",
                               {"upstream_detail": str(exc)})
