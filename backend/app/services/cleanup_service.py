import asyncio
import logging

import requests

from app.config import CORTEX_BASE_URL
from app.services.delete_service import run_delete
from app.services.document_registry import list_expired_documents, remove_document
from services.rag_client import is_available as is_cortex_available


LOGGER = logging.getLogger(__name__)

DOC_EXPIRY_HOURS = 24
CLEANUP_INTERVAL_SECONDS = 60 * 60


async def run_cleanup_once():
    expired_docs = list_expired_documents(max_age_hours=DOC_EXPIRY_HOURS)
    if not expired_docs:
        return

    cortex_ready = await asyncio.to_thread(is_cortex_available, CORTEX_BASE_URL, 3)
    if not cortex_ready:
        LOGGER.info(
            "Skipping expired document cleanup because Cortex is unavailable at %s; will retry later",
            CORTEX_BASE_URL,
        )
        return

    for doc in expired_docs:
        user_id = doc["user_id"]
        doc_id = doc["doc_id"]
        try:
            await asyncio.to_thread(run_delete, user_id, doc_id, "doclens")
            await asyncio.to_thread(remove_document, user_id, doc_id)
            LOGGER.info("Expired document deleted user_id=%s doc_id=%s", user_id, doc_id)
        except requests.RequestException as exc:
            LOGGER.warning(
                "Failed to delete expired document user_id=%s doc_id=%s error=%s",
                user_id, doc_id, exc,
            )


async def cleanup_forever(stop_event):
    while not stop_event.is_set():
        await run_cleanup_once()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=CLEANUP_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            continue
