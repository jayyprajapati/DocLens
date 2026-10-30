"""Document registry — maps a Brain ``doc_id`` to its owner, filename, and scope.

Two scopes implement DocLens' two upload flows:
  - ``global``  → uploaded as a shared Resource (left panel); queryable in *every*
                  chat for that user.
  - ``thread``  → uploaded inside a chat (paperclip); queryable *only* in that
                  ``thread_id``.

Both ingest into the same Brain collection under ``namespace=user_id``; the scope
distinction lives only here, and is enforced at query time by passing the right
union of ``doc_ids`` to Brain's retrieve.

Documents are temporary: ``sweep_expired`` deletes them (vectors + registry) once they are older
than the admin-configured ``uploads.expire_hours``.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import PurePath

from .. import analytics, brain_client, db, runtime
from ..extraction import ExtractionRejected, extract
from ..guardrails import scan_document

logger = logging.getLogger("doclens.documents")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _epoch(dt) -> int | None:
    return int(dt.timestamp()) if isinstance(dt, datetime) else None


def _public(doc: dict) -> dict:
    expire_h = runtime.current().uploads.expire_hours
    created = doc.get("created_at")
    return {
        "doc_id": doc["_id"],
        "filename": doc.get("filename") or f"doc-{doc['_id'][:8]}",
        "scope": doc.get("scope"),
        "thread_id": doc.get("thread_id"),
        "chunk_count": doc.get("chunk_count", 0),
        "pages": doc.get("pages"),
        "created_at": _epoch(created),
        "expires_at": _epoch(created + timedelta(hours=expire_h)) if expire_h and isinstance(created, datetime) else None,
        "warnings": doc.get("warnings", []),
    }


def ingest_document(
    *, user_id: str, file_bytes: bytes, filename: str, content_type: str, scope: str, thread_id: str | None = None
) -> dict:
    """Sniff → sandboxed extract → scan → ingest text into Brain (namespace=user_id) → record.

    * Identical bytes already visible in this scope (same chat, or a global resource) are reused
      instead of re-ingested — duplicate chunks would crowd the top results with one passage
      and show up as duplicate sources.
    * Raises ``ExtractionRejected`` for anything the upload policy refuses.
    * The document title is passed to Brain so every chunk is embedded and reranked as
      "title > heading" (contextual chunk headers).
    * Instruction-like text inside the document is flagged in ``warnings`` (and neutralised at
      prompt time — see guardrails.neutralize_source)."""
    cfg = runtime.current().uploads
    digest = hashlib.sha256(file_bytes).hexdigest()
    visible = [{"scope": "global"}]
    if scope == "thread":
        visible.append({"scope": "thread", "thread_id": thread_id})
    existing = db.documents().find_one({"user_id": user_id, "sha256": digest, "$or": visible})
    if existing:
        return {**_public(existing), "duplicate": True}

    if db.documents().count_documents({"user_id": user_id}) >= cfg.max_docs_per_user:
        raise ExtractionRejected(
            "doc_limit", f"You can keep up to {cfg.max_docs_per_user} documents at a time. Delete some to add more.", 409
        )

    ex = extract(filename, file_bytes, max_pages=cfg.max_pages, max_chars=cfg.max_chars)
    doc_id = str(uuid.uuid4())
    title = PurePath(filename).stem.replace("_", " ").replace("-", " ").strip()[:120] or "document"
    result = brain_client.ingest_text(text=ex.text, doc_id=doc_id, namespace=user_id, title=title)
    chunk_count = int(result.get("chunk_count", 0) or 0)
    if chunk_count == 0:
        # text came out but nothing was searchable (e.g. a script the chunker can't segment):
        # say so instead of reporting a successful upload that can never answer anything
        raise ExtractionRejected("not_indexed", "No searchable text could be indexed from this file.", 422)
    warnings = list(ex.warnings)
    if scan_document(ex.text):
        warnings.insert(0, "possible_prompt_injection")
    doc = {
        "_id": doc_id,
        "user_id": user_id,
        "filename": filename,
        "content_type": content_type,
        "kind": ex.kind,
        "scope": scope,
        "thread_id": thread_id if scope == "thread" else None,
        "chunk_count": chunk_count,
        "char_count": len(ex.text),
        "pages": ex.stats.get("pages"),
        "size_bytes": len(file_bytes),
        "sha256": digest,
        "warnings": warnings,
        "created_at": _now(),
    }
    db.documents().insert_one(doc)
    return {**_public(doc), "duplicate": False, "stats": ex.stats}


def owns(user_id: str, doc_id: str) -> bool:
    return db.documents().count_documents({"_id": doc_id, "user_id": user_id}, limit=1) > 0


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


def delete_document(user_id: str, doc_id: str, reason: str = "user") -> int | None:
    """Remove a single document's vectors (Brain) and registry row. Returns its chunk count,
    or None if the caller owns no such document."""
    owned = db.documents().find_one({"_id": doc_id, "user_id": user_id}, {"chunk_count": 1})
    if not owned:
        return None
    # Best-effort vector cleanup — a Brain hiccup shouldn't strand the registry row.
    try:
        brain_client.delete(doc_id=doc_id, namespace=user_id)
    except brain_client.BrainError:
        logger.warning("vector delete failed for doc %s", doc_id[:8])
    db.documents().delete_one({"_id": doc_id, "user_id": user_id})
    return int(owned.get("chunk_count", 0) or 0)


def delete_thread_documents(user_id: str, thread_id: str) -> tuple[int, int]:
    docs = chunks = 0
    for doc_id in thread_doc_ids(user_id, thread_id):
        c = delete_document(user_id, doc_id)
        if c is not None:
            docs, chunks = docs + 1, chunks + c
    return docs, chunks


def delete_all(user_id: str) -> tuple[int, int]:
    """Wipe every vector for the user (one namespace delete) and all registry rows.
    Returns (documents, chunks) removed."""
    chunks = sum(int(d.get("chunk_count", 0) or 0) for d in db.documents().find({"user_id": user_id}, {"chunk_count": 1}))
    try:
        brain_client.delete(namespace=user_id)
    except brain_client.BrainError:
        logger.warning("namespace delete failed for user %s", user_id[:8])
    res = db.documents().delete_many({"user_id": user_id})
    return res.deleted_count, chunks


def sweep_expired(batch: int = 200) -> int:
    """Delete documents older than ``uploads.expire_hours`` (0 = keep forever). Returns count."""
    hours = runtime.current().uploads.expire_hours
    if not hours:
        return 0
    cutoff = _now() - timedelta(hours=hours)
    removed = chunks = 0
    for d in db.documents().find({"created_at": {"$lt": cutoff}}, {"user_id": 1, "chunk_count": 1}).limit(batch):
        c = delete_document(d["user_id"], d["_id"], reason="expired")
        if c is not None:
            removed, chunks = removed + 1, chunks + c
    if removed:
        analytics.record("delete", reason="expired", docs=removed, chunks=chunks)
        logger.info("expired %d documents (%d chunks)", removed, chunks)
    return removed
