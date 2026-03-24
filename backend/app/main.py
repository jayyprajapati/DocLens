import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.services.cleanup_service import cleanup_forever


app = FastAPI(title="DocLens API")
app.state.cleanup_stop_event = asyncio.Event()
app.state.cleanup_task = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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
