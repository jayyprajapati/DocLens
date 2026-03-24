import asyncio
import logging

import requests

from app.services.delete_service import run_delete
from app.services.policy_state import get_expired_documents, remove_document


LOGGER = logging.getLogger(__name__)

DOC_EXPIRY_HOURS = 24
CLEANUP_INTERVAL_SECONDS = 60 * 60


async def run_cleanup_once():
    expired_docs = get_expired_documents(DOC_EXPIRY_HOURS * 60 * 60)

    if not expired_docs:
        return

    for expired_doc in expired_docs:
        user_id = expired_doc["user_id"]
        doc_id = expired_doc["doc_id"]

        try:
            await asyncio.to_thread(run_delete, user_id, doc_id, "doclens")
            await asyncio.to_thread(remove_document, user_id, doc_id)
            LOGGER.info("Expired document deleted", extra={"user_id": user_id, "doc_id": doc_id})
        except requests.RequestException as exc:
            LOGGER.warning(
                "Failed to delete expired document", extra={"user_id": user_id, "doc_id": doc_id, "error": str(exc)}
            )


async def cleanup_forever(stop_event):
    while not stop_event.is_set():
        await run_cleanup_once()

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=CLEANUP_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            continue
