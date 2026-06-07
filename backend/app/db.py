"""MongoDB access — DocLens application state only.

Three collections (all prefixed ``doclens_`` so they're safe to share a database
with other apps):

  - ``doclens_threads``   — chat sessions: {_id, user_id, title, created_at, updated_at, message_count}
  - ``doclens_messages``  — turns: {_id, thread_id, user_id, role, content, citations[], created_at}
  - ``doclens_documents`` — registry mapping a Brain ``doc_id`` to its owner, filename,
                            and scope. scope is "global" (queryable in every chat) or
                            "thread" (only inside thread_id). _id IS the Brain doc_id.

Brain holds none of this — it only stores vectors keyed by namespace=user_id and
doc_id. The mapping of doc_id → filename/scope/thread lives here.
"""
from __future__ import annotations

import logging

from pymongo import ASCENDING, DESCENDING, MongoClient

from .config import settings

logger = logging.getLogger("doclens.db")

_client: MongoClient | None = None


def _get_client() -> MongoClient:
    global _client
    if _client is None:
        # serverSelectionTimeoutMS keeps a dead Mongo from hanging requests forever.
        _client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=8000, tz_aware=True)
    return _client


def get_db():
    return _get_client()[settings.mongo_db]


def threads():
    return get_db()["doclens_threads"]


def messages():
    return get_db()["doclens_messages"]


def documents():
    return get_db()["doclens_documents"]


def ensure_indexes() -> None:
    """Create the indexes the queries rely on. Best-effort — a transient Mongo
    outage at startup must not crash the app."""
    try:
        threads().create_index([("user_id", ASCENDING), ("updated_at", DESCENDING)])
        messages().create_index([("thread_id", ASCENDING), ("created_at", ASCENDING)])
        documents().create_index([("user_id", ASCENDING), ("scope", ASCENDING)])
        documents().create_index([("thread_id", ASCENDING)])
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not create Mongo indexes (will retry lazily): %s", exc)
