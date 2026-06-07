"""Chat sessions ("threads") and their messages — DocLens-owned state in Mongo.

A thread groups a conversation and the documents attached *to that chat only*.
Deleting a thread also removes its messages and its chat-scoped documents (and
their vectors in Brain). Global resources are never touched by thread deletion.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .. import db


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _epoch(dt) -> int | None:
    if not dt:
        return None
    if isinstance(dt, datetime):
        return int(dt.timestamp())
    return None


def _public(thread: dict) -> dict:
    return {
        "id": thread["_id"],
        "title": thread.get("title") or "New chat",
        "message_count": int(thread.get("message_count", 0)),
        "created_at": _epoch(thread.get("created_at")),
        "updated_at": _epoch(thread.get("updated_at")),
    }


def create_thread(user_id: str, title: str = "New chat") -> dict:
    now = _now()
    doc = {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "title": (title or "New chat").strip()[:120] or "New chat",
        "message_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    db.threads().insert_one(doc)
    return _public(doc)


def get_thread_raw(user_id: str, thread_id: str) -> dict | None:
    return db.threads().find_one({"_id": thread_id, "user_id": user_id})


def list_threads(user_id: str) -> list[dict]:
    cursor = db.threads().find({"user_id": user_id}).sort("updated_at", -1)
    return [_public(t) for t in cursor]


def touch_thread(user_id: str, thread_id: str, inc_messages: int = 0, title: str | None = None) -> None:
    update: dict = {"$set": {"updated_at": _now()}}
    if inc_messages:
        update["$inc"] = {"message_count": inc_messages}
    if title is not None:
        update["$set"]["title"] = (title or "").strip()[:120] or "New chat"
    db.threads().update_one({"_id": thread_id, "user_id": user_id}, update)


def rename_thread(user_id: str, thread_id: str, title: str) -> dict | None:
    db.threads().update_one(
        {"_id": thread_id, "user_id": user_id},
        {"$set": {"title": (title or "").strip()[:120] or "New chat", "updated_at": _now()}},
    )
    t = get_thread_raw(user_id, thread_id)
    return _public(t) if t else None


def add_message(thread_id: str, user_id: str, role: str, content: str, citations: list | None = None) -> dict:
    doc = {
        "_id": str(uuid.uuid4()),
        "thread_id": thread_id,
        "user_id": user_id,
        "role": role,
        "content": content,
        "citations": citations or [],
        "created_at": _now(),
    }
    db.messages().insert_one(doc)
    return doc


def recent_messages(thread_id: str, limit: int = 8) -> list[dict]:
    """Most recent turns in chronological order (for conversational context)."""
    cursor = db.messages().find({"thread_id": thread_id}).sort("created_at", -1).limit(limit)
    rows = list(cursor)
    rows.reverse()
    return [{"role": r.get("role"), "content": r.get("content", "")} for r in rows]


def thread_messages(user_id: str, thread_id: str) -> list[dict]:
    cursor = db.messages().find({"thread_id": thread_id, "user_id": user_id}).sort("created_at", 1)
    return [
        {
            "id": r["_id"],
            "role": r.get("role"),
            "content": r.get("content", ""),
            "citations": r.get("citations", []),
            "created_at": _epoch(r.get("created_at")),
        }
        for r in cursor
    ]


def delete_thread(user_id: str, thread_id: str) -> None:
    """Remove the thread, its messages, and its chat-scoped documents (vectors
    included). Caller handles Brain vector deletion for the docs."""
    db.messages().delete_many({"thread_id": thread_id, "user_id": user_id})
    db.threads().delete_one({"_id": thread_id, "user_id": user_id})


def derive_title(query: str) -> str:
    """A short, human title from the first user question."""
    clean = " ".join((query or "").split())
    if not clean:
        return "New chat"
    words = clean.split(" ")
    title = " ".join(words[:8])
    if len(words) > 8 or len(title) > 60:
        title = title[:58].rstrip() + "…"
    return title
