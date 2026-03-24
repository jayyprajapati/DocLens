import os
import tempfile

import requests
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.services.generate_service import run_generate
from app.services.ingest_service import run_ingest
from app.services.query_service import run_query
from app.services.delete_service import run_delete, run_delete_all
from app.services.document_registry import register_document, remove_all_documents, remove_document


router = APIRouter()


class QueryRequest(BaseModel):
    query: str
    user_id: str
    api_key: str | None = None
    model: str | None = None


class GenerateRequest(BaseModel):
    prompt: str


class DeleteRequest(BaseModel):
    user_id: str
    doc_id: str


class DeleteAllRequest(BaseModel):
    user_id: str


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


@router.post("/query")
def query_endpoint(request: QueryRequest):
    llm_config = {}
    if request.api_key:
        llm_config["api_key"] = request.api_key
    if request.model:
        llm_config["model"] = request.model

    try:
        return run_query(
            query=request.query,
            user_id=request.user_id,
            app_name="doclens",
            llm_config=llm_config or None,
        )
    except requests.HTTPError as exc:
        detail = exc.response.text if exc.response is not None else str(exc)
        raise HTTPException(status_code=502, detail=detail) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc



@router.post("/ingest")
async def ingest_endpoint(file: UploadFile = File(...), user_id: str = Form(...)):
    temp_path = None

    try:
        suffix = os.path.splitext(file.filename or "")[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name
            content = await file.read()
            temp_file.write(content)

        result = run_ingest(
            file_path=temp_path,
            user_id=user_id,
            app_name="doclens",
        )

        doc_id = _extract_doc_id(result)
        if doc_id:
            register_document(user_id=user_id, doc_id=doc_id)

        return {"status": "success", "result": result, "doc_id": doc_id}
    except requests.HTTPError as exc:
        detail = exc.response.text if exc.response is not None else str(exc)
        raise HTTPException(status_code=502, detail=detail) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await file.close()
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


@router.post("/generate")
def generate_endpoint(request: GenerateRequest):
    try:
        return run_generate(prompt=request.prompt)
    except requests.HTTPError as exc:
        detail = exc.response.text if exc.response is not None else str(exc)
        raise HTTPException(status_code=502, detail=detail) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/delete")
def delete_endpoint(request: DeleteRequest):
    try:
        result = run_delete(
            user_id=request.user_id,
            doc_id=request.doc_id,
            app_name="doclens",
        )
        remove_document(user_id=request.user_id, doc_id=request.doc_id)
        return {"status": "success", "result": result}
    except requests.HTTPError as exc:
        detail = exc.response.text if exc.response is not None else str(exc)
        raise HTTPException(status_code=502, detail=detail) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/delete_all")
def delete_all_endpoint(request: DeleteAllRequest):
    try:
        result = run_delete_all(
            user_id=request.user_id,
            app_name="doclens",
        )
        remove_all_documents(user_id=request.user_id)
        return {"status": "success", "result": result}
    except requests.HTTPError as exc:
        detail = exc.response.text if exc.response is not None else str(exc)
        raise HTTPException(status_code=502, detail=detail) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc