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

Operational collections (read by the admin panel through /internal/admin):

  - ``doclens_settings`` — one doc ``_id="runtime"``: live, admin-editable settings (runtime.py)
  - ``doclens_events``   — usage analytics (chat / upload / delete / session / rejected …),
                           expired by a TTL index after EVENTS_RETENTION_DAYS
  - ``doclens_usage``    — daily quota counters (hosted-mode chats, uploads), TTL-expired
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


def settings_coll():
    return get_db()["doclens_settings"]


def events():
    return get_db()["doclens_events"]


def usage():
    return get_db()["doclens_usage"]


def ensure_indexes() -> None:
    """Create the indexes the queries rely on. Best-effort — a transient Mongo
    outage at startup must not crash the app."""
    try:
        threads().create_index([("user_id", ASCENDING), ("updated_at", DESCENDING)])
        messages().create_index([("thread_id", ASCENDING), ("created_at", ASCENDING)])
        documents().create_index([("user_id", ASCENDING), ("scope", ASCENDING)])
        documents().create_index([("thread_id", ASCENDING)])
        documents().create_index([("created_at", ASCENDING)])
        events().create_index([("ts", ASCENDING)], expireAfterSeconds=settings.events_retention_days * 86400)
        events().create_index([("kind", ASCENDING), ("ts", DESCENDING)])
        events().create_index([("user", ASCENDING), ("ts", DESCENDING)])
        usage().create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not create Mongo indexes (will retry lazily): %s", exc)
