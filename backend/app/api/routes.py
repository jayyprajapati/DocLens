import os
import tempfile

import requests
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.services.generate_service import run_generate
from app.services.ingest_service import run_ingest
from app.services.query_service import run_query


router = APIRouter()


class QueryRequest(BaseModel):
    query: str
    user_id: str
    api_key: str | None = None
    model: str | None = None


class GenerateRequest(BaseModel):
    prompt: str


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
        return {"status": "success", "result": result}
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