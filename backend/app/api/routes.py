import os
import tempfile
import time

import requests
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pypdf import PdfReader
from pydantic import BaseModel, Field

from app.services.delete_service import run_delete, run_delete_all
from app.services.generate_service import run_generate
from app.services.ingest_service import run_ingest
from app.services.policy_state import (
    can_ingest,
    can_query,
    get_limits,
    get_usage_payload,
    record_query,
    register_document,
    remove_all_documents,
    remove_document,
)
from app.services.query_service import run_query


router = APIRouter()

FREE_MAX_PAGES = 3


class QueryRequest(BaseModel):
    query: str
    user_id: str
    api_key: str | None = None
    model: str | None = None


class GenerateRequest(BaseModel):
    prompt: str
    user_id: str | None = None
    api_key: str | None = None


class DeleteRequest(BaseModel):
    user_id: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)
    api_key: str | None = None


class DeleteAllRequest(BaseModel):
    user_id: str = Field(min_length=1)
    api_key: str | None = None


def _extract_doc_id(ingest_result):
    if not isinstance(ingest_result, dict):
        return None

    candidates = [
        ingest_result.get("doc_id"),
        ingest_result.get("document_id"),
        ingest_result.get("id"),
    ]

    nested_result = ingest_result.get("result")
    if isinstance(nested_result, dict):
        candidates.extend(
            [
                nested_result.get("doc_id"),
                nested_result.get("document_id"),
                nested_result.get("id"),
            ]
        )

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    return None


def _safe_duration(value, default_value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return round(float(default_value), 4)

    if parsed < 0:
        return round(float(default_value), 4)

    return round(parsed, 4)


def _build_meta(raw_meta, elapsed_ms):
    if not isinstance(raw_meta, dict):
        raw_meta = {}

    return {
        "retrieval_time": _safe_duration(raw_meta.get("retrieval_time"), elapsed_ms),
        "generation_time": _safe_duration(raw_meta.get("generation_time"), 0),
    }


def _error_response(status_code, error_code, message, extra=None):
    payload = {
        "error": error_code,
        "message": message,
        "detail": message,
    }

    if isinstance(extra, dict):
        payload.update(extra)

    return JSONResponse(status_code=status_code, content=payload)


def _extract_upstream_error(exc):
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.text
    return str(exc)


def _count_file_pages(file_path, filename):
    suffix = os.path.splitext(filename or "")[1].lower()
    if suffix != ".pdf":
        return 1

    try:
        reader = PdfReader(file_path)
        return len(reader.pages)
    except Exception:
        return None


def _anonymous_usage_payload(api_key=None):
    limits = get_limits(api_key)
    return {
        "docs": 0,
        "queries": 0,
        "limits": {
            "docs": limits["docs"],
            "queries": limits["queries"],
        },
    }


@router.post("/query")
def query_endpoint(request: QueryRequest):
    if not can_query(request.user_id, request.api_key):
        return _error_response(
            status_code=429,
            error_code="QUOTA_EXCEEDED",
            message="Free quota exhausted. Use your API key to continue.",
            extra={"usage": get_usage_payload(request.user_id, request.api_key)},
        )

    llm_config = {}
    if request.api_key:
        llm_config["api_key"] = request.api_key
    if request.model:
        llm_config["model"] = request.model

    start = time.perf_counter()

    try:
        result = run_query(
            query=request.query,
            user_id=request.user_id,
            app_name="doclens",
            llm_config=llm_config or None,
        )
    except requests.HTTPError as exc:
        return _error_response(
            status_code=502,
            error_code="upstream_query_error",
            message="Failed to run document query.",
            extra={"upstream_detail": _extract_upstream_error(exc)},
        )
    except requests.RequestException as exc:
        return _error_response(
            status_code=502,
            error_code="upstream_query_error",
            message="Failed to run document query.",
            extra={"upstream_detail": _extract_upstream_error(exc)},
        )

    elapsed_ms = (time.perf_counter() - start) * 1000
    record_query(request.user_id)

    payload = dict(result) if isinstance(result, dict) else {"result": result}
    payload["meta"] = _build_meta(payload.get("meta"), elapsed_ms)
    payload["usage"] = get_usage_payload(request.user_id, request.api_key)
    return payload



@router.post("/ingest")
async def ingest_endpoint(file: UploadFile = File(...), user_id: str = Form(...), api_key: str | None = Form(None)):
    start = time.perf_counter()

    if not can_ingest(user_id, api_key):
        return _error_response(
            status_code=429,
            error_code="QUOTA_EXCEEDED",
            message="Free quota exhausted. Use your API key to continue.",
            extra={"usage": get_usage_payload(user_id, api_key)},
        )

    temp_path = None
    page_count = None

    try:
        suffix = os.path.splitext(file.filename or "")[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name
            content = await file.read()
            temp_file.write(content)

        if not (api_key or "").strip():
            page_count = _count_file_pages(temp_path, file.filename)
            if page_count is None:
                return _error_response(
                    status_code=400,
                    error_code="page_count_unavailable",
                    message="Unable to determine page count for this file.",
                )

            if page_count > FREE_MAX_PAGES:
                return _error_response(
                    status_code=400,
                    error_code="page_limit_exceeded",
                    message="Free tier supports up to 3 pages per document.",
                    extra={"page_count": page_count, "max_pages": FREE_MAX_PAGES},
                )

        result = run_ingest(
            file_path=temp_path,
            user_id=user_id,
            app_name="doclens",
        )

        doc_id = _extract_doc_id(result)
        if not doc_id:
            return _error_response(
                status_code=500,
                error_code="missing_doc_id",
                message="Ingest response missing doc_id.",
            )

        register_document(user_id=user_id, doc_id=doc_id, filename=file.filename)

        elapsed_ms = (time.perf_counter() - start) * 1000

        return {
            "status": "success",
            "doc_id": doc_id,
            "usage": get_usage_payload(user_id, api_key),
            "meta": _build_meta({}, elapsed_ms),
        }
    except requests.HTTPError as exc:
        return _error_response(
            status_code=502,
            error_code="upstream_ingest_error",
            message="Failed to ingest document.",
            extra={"upstream_detail": _extract_upstream_error(exc)},
        )
    except requests.RequestException as exc:
        return _error_response(
            status_code=502,
            error_code="upstream_ingest_error",
            message="Failed to ingest document.",
            extra={"upstream_detail": _extract_upstream_error(exc)},
        )
    finally:
        await file.close()
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


@router.post("/generate")
def generate_endpoint(request: GenerateRequest):
    start = time.perf_counter()

    try:
        result = run_generate(prompt=request.prompt)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "status": "success",
            "result": result,
            "usage": get_usage_payload(request.user_id, request.api_key)
            if request.user_id
            else _anonymous_usage_payload(request.api_key),
            "meta": _build_meta({}, elapsed_ms),
        }
    except requests.HTTPError as exc:
        return _error_response(
            status_code=502,
            error_code="upstream_generate_error",
            message="Failed to generate response.",
            extra={"upstream_detail": _extract_upstream_error(exc)},
        )
    except requests.RequestException as exc:
        return _error_response(
            status_code=502,
            error_code="upstream_generate_error",
            message="Failed to generate response.",
            extra={"upstream_detail": _extract_upstream_error(exc)},
        )


@router.post("/delete")
def delete_endpoint(request: DeleteRequest):
    start = time.perf_counter()

    try:
        result = run_delete(
            user_id=request.user_id,
            doc_id=request.doc_id,
            app_name="doclens",
        )
        remove_document(user_id=request.user_id, doc_id=request.doc_id)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "status": "success",
            "result": result,
            "usage": get_usage_payload(request.user_id, request.api_key),
            "meta": _build_meta({}, elapsed_ms),
        }
    except requests.HTTPError as exc:
        return _error_response(
            status_code=502,
            error_code="upstream_delete_error",
            message="Failed to delete document.",
            extra={"upstream_detail": _extract_upstream_error(exc)},
        )
    except requests.RequestException as exc:
        return _error_response(
            status_code=502,
            error_code="upstream_delete_error",
            message="Failed to delete document.",
            extra={"upstream_detail": _extract_upstream_error(exc)},
        )


@router.post("/delete_all")
def delete_all_endpoint(request: DeleteAllRequest):
    start = time.perf_counter()

    try:
        result = run_delete_all(
            user_id=request.user_id,
            app_name="doclens",
        )
        remove_all_documents(user_id=request.user_id)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "status": "success",
            "result": result,
            "usage": get_usage_payload(request.user_id, request.api_key),
            "meta": _build_meta({}, elapsed_ms),
        }
    except requests.HTTPError as exc:
        return _error_response(
            status_code=502,
            error_code="upstream_delete_error",
            message="Failed to delete documents.",
            extra={"upstream_detail": _extract_upstream_error(exc)},
        )
    except requests.RequestException as exc:
        return _error_response(
            status_code=502,
            error_code="upstream_delete_error",
            message="Failed to delete documents.",
            extra={"upstream_detail": _extract_upstream_error(exc)},
        )
