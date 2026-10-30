"""DocLens API — FastAPI entrypoint.

DocLens orchestrates Brain (RAG/LLM) and owns its own state in MongoDB. It holds
no embeddings: retrieval/generation are delegated to Brain, and the user's BYOK key
(or, in hosted mode, the server's own Ollama key) is forwarded per request.
"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import admin
from .api.routes import router
from .config import settings
from .db import ensure_indexes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("doclens")

_SWEEP_EVERY_S = 600
_stop = threading.Event()


def _sweeper() -> None:
    """Background loop: delete documents past their expiry (privacy promise + bounded storage)."""
    from .services.documents import sweep_expired

    while not _stop.wait(_SWEEP_EVERY_S):
        try:
            sweep_expired()
        except Exception:  # noqa: BLE001 — never let the loop die
            logger.exception("document expiry sweep failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Best-effort: create Mongo indexes. A transient outage won't block startup.
    ensure_indexes()
    if not settings.is_dev and not settings.session_secret:
        logger.error("SESSION_SECRET is not set: every request will be refused until it is (see DEPLOYMENT.md)")
    t = threading.Thread(target=_sweeper, name="doc-expiry", daemon=True)
    t.start()
    yield
    _stop.set()


_docs_kwargs = {} if settings.is_dev else {"docs_url": None, "redoc_url": None, "openapi_url": None}

app = FastAPI(title="DocLens API", version="2.1.0", lifespan=lifespan, **_docs_kwargs)


@app.middleware("http")
async def guard_body_size(request: Request, call_next):
    """Refuse oversized bodies from the declared length before reading them. Uploads are capped
    again while streaming (routes._read_upload); Caddy's request_body limit is the outer wall."""
    length = request.headers.get("content-length")
    limit = (60 if request.url.path in ("/ingest", "/resources") else 1) * 1024 * 1024
    if length and length.isdigit() and int(length) > limit:
        return JSONResponse(status_code=413, content={"error": "too_large", "message": "Request too large.", "detail": "Request too large."})
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,  # bearer tokens, no cookies
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Provider-Key"],
)

app.include_router(router)
app.include_router(admin.router)
