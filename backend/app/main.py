"""DocLens API — FastAPI entrypoint.

DocLens orchestrates Brain (RAG/LLM) and owns its own state in MongoDB. It holds
no embeddings or model keys: retrieval/generation are delegated to Brain, and the
user's BYOK key is forwarded per-request.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import settings
from .db import ensure_indexes

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Best-effort: create Mongo indexes. A transient outage won't block startup.
    ensure_indexes()
    yield


_docs_kwargs = {} if settings.is_dev else {"docs_url": None, "redoc_url": None, "openapi_url": None}

app = FastAPI(title="DocLens API", version="2.0.0", lifespan=lifespan, **_docs_kwargs)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
