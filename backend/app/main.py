import asyncio
import logging
import os
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.api.routes import router
from app.services.cleanup_service import cleanup_forever


LOGGER = logging.getLogger(__name__)


_env = os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or ""
_is_dev = str(_env).strip().lower() in ("dev", "development", "local")
_DOCS_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi",
    "/openapi.json",
    "/docs/oauth2-redirect",
)
_DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:3000",
    "https://doclens.jayprajapati.dev",
)


def _build_allowed_origins():
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
    if raw:
        entries = tuple(origin.strip() for origin in raw.split(",") if origin.strip())
        if entries:
            return entries
    return _DEFAULT_ALLOWED_ORIGINS


_ALLOWED_ORIGINS = _build_allowed_origins()


def _is_docs_path(path):
    for prefix in _DOCS_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def _extract_origin_from_referer(referer):
    try:
        parsed = urlparse(referer)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        pass
    return ""


def _origin_allowed(origin):
    try:
        parsed_origin = urlparse(origin.rstrip("/").lower())
        for allowed in _ALLOWED_ORIGINS:
            parsed_allowed = urlparse(allowed.rstrip("/").lower())
            if parsed_allowed.scheme != parsed_origin.scheme:
                continue
            if parsed_allowed.netloc == parsed_origin.netloc:
                return True
            if parsed_allowed.hostname and parsed_allowed.hostname.startswith("*."):
                suffix = parsed_allowed.hostname[2:]
                if parsed_allowed.port != parsed_origin.port:
                    continue
                origin_host = parsed_origin.hostname or ""
                if origin_host.endswith("." + suffix):
                    subdomain = origin_host[: -(len(suffix) + 1)]
                    if subdomain and "." not in subdomain:
                        return True
    except Exception:
        pass
    return False

app = FastAPI(
    title="DocLens API",
    **({} if _is_dev else {"docs_url": None, "redoc_url": None, "openapi_url": None}),
)
app.state.cleanup_stop_event = asyncio.Event()
app.state.cleanup_task = None


@app.middleware("http")
async def block_docs_in_non_dev(request: Request, call_next):
    if not _is_dev:
        if _is_docs_path(request.url.path):
            LOGGER.warning(
                "Blocked documentation endpoint path=%s host=%s",
                request.url.path,
                request.headers.get("host", ""),
            )
            return Response(status_code=404)

        if request.method != "OPTIONS":
            origin = (request.headers.get("origin") or "").strip()
            referer = (request.headers.get("referer") or "").strip()
            effective_origin = origin or _extract_origin_from_referer(referer)

            if not effective_origin or not _origin_allowed(effective_origin):
                LOGGER.warning(
                    "Blocked direct API request path=%s host=%s origin=%s referer=%s",
                    request.url.path,
                    request.headers.get("host", ""),
                    origin,
                    referer,
                )
                return Response(status_code=403)
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
async def startup_event():
    app.state.cleanup_stop_event.clear()
    app.state.cleanup_task = asyncio.create_task(cleanup_forever(app.state.cleanup_stop_event))


@app.on_event("shutdown")
async def shutdown_event():
    app.state.cleanup_stop_event.set()
    cleanup_task = app.state.cleanup_task
    if cleanup_task:
        await cleanup_task
