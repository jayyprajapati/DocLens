import asyncio
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.services.cleanup_service import cleanup_forever


_env = os.getenv("APP_ENV") or os.getenv("ENV") or os.getenv("PYTHON_ENV") or "development"
_is_prod = str(_env).lower() in ("production", "prod")

app = FastAPI(
    title="DocLens API",
    **({"docs_url": None, "redoc_url": None, "openapi_url": None} if _is_prod else {}),
)
app.state.cleanup_stop_event = asyncio.Event()
app.state.cleanup_task = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://doclens.jayprajapati.dev"],
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
