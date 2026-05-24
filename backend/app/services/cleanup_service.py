import asyncio
import logging

from app.config import CORTEX_BASE_URL
from services.rag_client import is_available as is_cortex_available


LOGGER = logging.getLogger(__name__)

CLEANUP_INTERVAL_SECONDS = 60 * 60


async def run_cleanup_once():
    # Document expiry is now managed by Cortex; no local registry to clean.
    pass


async def cleanup_forever(stop_event):
    while not stop_event.is_set():
        await run_cleanup_once()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=CLEANUP_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            continue
