"""Document registry — maps a Brain ``doc_id`` to its owner, filename, and scope.

Two scopes implement DocLens' two upload flows:
  - ``global``  → uploaded as a shared Resource (left panel); queryable in *every*
                  chat for that user.
  - ``thread``  → uploaded inside a chat (paperclip); queryable *only* in that
                  ``thread_id``.

Both ingest into the same Brain collection under ``namespace=user_id``; the scope
distinction lives only here, and is enforced at query time by passing the right
union of ``doc_ids`` to Brain's retrieve.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .. import brain_client, db


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _epoch(dt) -> int | None:
    return int(dt.timestamp()) if isinstance(dt, datetime) else None


def _public(doc: dict) -> dict:
    return {
        "doc_id": doc["_id"],
        "filename": doc.get("filename") or f"doc-{doc['_id'][:8]}",
        "scope": doc.get("scope"),
        "thread_id": doc.get("thread_id"),
        "chunk_count": doc.get("chunk_count", 0),
        "created_at": _epoch(doc.get("created_at")),
    }


def ingest_document(
    *, user_id: str, file_bytes: bytes, filename: str, content_type: str, scope: str, thread_id: str | None = None
) -> dict:
    """Ingest into Brain (namespace=user_id) and record the mapping. Returns the
    public doc dict including ``chunk_count``."""
    doc_id = str(uuid.uuid4())
    result = brain_client.extract_and_ingest(
        file_bytes=file_bytes,
        filename=filename,
        content_type=content_type,
        doc_id=doc_id,
        namespace=user_id,
    )
    chunk_count = int(result.get("chunk_count", 0) or 0)
    doc = {
        "_id": doc_id,
        "user_id": user_id,
        "filename": filename,
        "content_type": content_type,
        "scope": scope,
        "thread_id": thread_id if scope == "thread" else None,
        "chunk_count": chunk_count,
        "char_count": int(result.get("char_count", 0) or 0),
        "created_at": _now(),
    }
    db.documents().insert_one(doc)
    return _public(doc)


def list_documents(user_id: str, *, scope: str | None = None, thread_id: str | None = None) -> list[dict]:
    query: dict = {"user_id": user_id}
    if scope:
        query["scope"] = scope
    if thread_id:
        query["thread_id"] = thread_id
    cursor = db.documents().find(query).sort("created_at", 1)
    return [_public(d) for d in cursor]


def global_doc_ids(user_id: str) -> list[str]:
    cursor = db.documents().find({"user_id": user_id, "scope": "global"}, {"_id": 1})
    return [d["_id"] for d in cursor]


def thread_doc_ids(user_id: str, thread_id: str) -> list[str]:
    cursor = db.documents().find({"user_id": user_id, "thread_id": thread_id}, {"_id": 1})
    return [d["_id"] for d in cursor]


def filename_map(user_id: str, doc_ids: list[str]) -> dict[str, str]:
    if not doc_ids:
        return {}
    cursor = db.documents().find({"user_id": user_id, "_id": {"$in": list(set(doc_ids))}}, {"filename": 1})
    return {d["_id"]: d.get("filename") or "document" for d in cursor}


def delete_document(user_id: str, doc_id: str) -> bool:
    """Remove a single document's vectors (Brain) and registry row. Returns True
    if a row was removed."""
    owned = db.documents().find_one({"_id": doc_id, "user_id": user_id})
    if not owned:
        return False
    # Best-effort vector cleanup — a Brain hiccup shouldn't strand the registry row.
    try:
        brain_client.delete(doc_id=doc_id, namespace=user_id)
    except brain_client.BrainError:
        pass
    db.documents().delete_one({"_id": doc_id, "user_id": user_id})
    return True


def delete_thread_documents(user_id: str, thread_id: str) -> None:
    for doc_id in thread_doc_ids(user_id, thread_id):
        delete_document(user_id, doc_id)


def delete_all(user_id: str) -> int:
    """Wipe every vector for the user (one namespace delete) and all registry
    rows. Returns the number of registry rows removed."""
    try:
        brain_client.delete(namespace=user_id)
    except brain_client.BrainError:
        pass
    res = db.documents().delete_many({"user_id": user_id})
    return res.deleted_count
