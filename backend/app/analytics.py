"""Usage analytics + daily quotas.

``record`` writes one row to ``doclens_events`` per thing that happened (a chat turn, an upload,
a rejected upload, a deletion, a new session). Rows carry the pseudonymous user id and an IP
*hash* — never raw IPs or provider keys. Recording is best-effort: analytics can never fail a
user request.

``consume`` is an atomic daily counter in ``doclens_usage`` (TTL-expired), used for the hosted
mode quotas and the daily upload cap. Counters live in Mongo so they survive restarts.

``stats`` / ``list_events`` / ``list_users`` back the admin panel (via /internal/admin).
"""
from __future__ import annotations

import logging
import re
import statistics
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument

from . import db

logger = logging.getLogger("doclens.analytics")

MAX_QUERY = 2000
MAX_ANSWER = 6000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _day(dt: datetime | None = None) -> str:
    return (dt or _now()).strftime("%Y-%m-%d")


def record(kind: str, **fields) -> None:
    doc = {"kind": kind, "ts": _now()}
    for k, v in fields.items():
        if v is None:
            continue
        if k == "query" and isinstance(v, str):
            v = v[:MAX_QUERY]
        elif k == "answer" and isinstance(v, str):
            v = v[:MAX_ANSWER]
        doc[k] = v
    try:
        db.events().insert_one(doc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("analytics write failed (%s): %s", kind, exc)


# ── quotas ───────────────────────────────────────────────────────────────────


def consume(bucket: str, key: str, limit: int) -> tuple[bool, int]:
    """Count one use of ``bucket`` for ``key`` today. Returns (allowed, used_after).
    ``limit <= 0`` blocks everything (a quota of zero means "off")."""
    if limit <= 0:
        return False, 0
    day = _day()
    try:
        row = db.usage().find_one_and_update(
            {"_id": f"{day}:{bucket}:{key}"},
            {"$inc": {"n": 1}, "$setOnInsert": {"expires_at": _now() + timedelta(days=2), "bucket": bucket, "day": day}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except Exception as exc:  # noqa: BLE001 — fail closed for spend-bearing quotas
        logger.error("quota store unavailable: %s", exc)
        return False, 0
    n = int(row.get("n", 0))
    return n <= limit, n


def used(bucket: str, key: str) -> int:
    try:
        row = db.usage().find_one({"_id": f"{_day()}:{bucket}:{key}"})
    except Exception:  # noqa: BLE001
        return 0
    return int((row or {}).get("n", 0))


# ── admin views ──────────────────────────────────────────────────────────────


def _pct(vals: list[float], p: float) -> int | None:
    if not vals:
        return None
    vals = sorted(vals)
    return int(vals[min(len(vals) - 1, int(round(p / 100 * (len(vals) - 1))))])


def stats(days: int = 30) -> dict:
    ev = db.events()
    now = _now()
    since = now - timedelta(days=days)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def count(q: dict) -> int:
        return ev.count_documents(q)

    chats_q = {"kind": "chat"}
    users_all = set(ev.distinct("user", {"user": {"$ne": None}})) | set(db.documents().distinct("user_id"))
    active = {
        "today": len(ev.distinct("user", {"ts": {"$gte": day_start}})),
        "7d": len(ev.distinct("user", {"ts": {"$gte": now - timedelta(days=7)}})),
        "30d": len(ev.distinct("user", {"ts": {"$gte": now - timedelta(days=30)}})),
    }
    recent = list(ev.find({**chats_q, "ts": {"$gte": since}}, {"total_ms": 1, "grounded": 1, "abstained": 1, "blocked": 1, "mode": 1, "model": 1, "error": 1}).sort("ts", -1).limit(5000))
    lat = [r["total_ms"] for r in recent if isinstance(r.get("total_ms"), (int, float)) and not r.get("blocked")]
    n = len(recent) or 1
    models: dict[str, int] = {}
    for r in recent:
        if r.get("model"):
            models[r["model"]] = models.get(r["model"], 0) + 1
    guard = list(ev.aggregate([
        {"$match": {**chats_q, "ts": {"$gte": since}, "guardrails.0": {"$exists": True}}},
        {"$unwind": "$guardrails"},
        {"$group": {"_id": "$guardrails", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}}, {"$limit": 20},
    ]))
    rejects = list(ev.aggregate([
        {"$match": {"kind": "upload_rejected", "ts": {"$gte": since}}},
        {"$group": {"_id": "$reason", "n": {"$sum": 1}}}, {"$sort": {"n": -1}},
    ]))
    series = list(ev.aggregate([
        {"$match": {"ts": {"$gte": since}, "kind": {"$in": ["chat", "upload", "session"]}}},
        {"$group": {
            "_id": {"d": {"$dateToString": {"format": "%Y-%m-%d", "date": "$ts"}}, "k": "$kind"},
            "n": {"$sum": 1}, "users": {"$addToSet": "$user"},
        }},
    ]))
    by_day: dict[str, dict] = {}
    for row in series:
        d = by_day.setdefault(row["_id"]["d"], {"day": row["_id"]["d"], "chat": 0, "upload": 0, "session": 0, "users": set()})
        d[row["_id"]["k"]] = row["n"]
        d["users"].update(u for u in row["users"] if u)
    daily = [{**v, "users": len(v["users"])} for _, v in sorted(by_day.items())]

    docs_live = list(db.documents().aggregate([
        {"$group": {"_id": None, "docs": {"$sum": 1}, "chunks": {"$sum": "$chunk_count"}, "chars": {"$sum": "$char_count"}}},
    ]))
    live = docs_live[0] if docs_live else {"docs": 0, "chunks": 0, "chars": 0}
    uploads_ok = list(ev.aggregate([
        {"$match": {"kind": "upload"}},
        {"$group": {"_id": None, "n": {"$sum": 1}, "chunks": {"$sum": "$chunks"}, "pages": {"$sum": "$pages"}}},
    ]))
    up = uploads_ok[0] if uploads_ok else {"n": 0, "chunks": 0, "pages": 0}
    deletes = list(ev.aggregate([
        {"$match": {"kind": "delete"}},
        {"$group": {"_id": "$reason", "docs": {"$sum": "$docs"}, "chunks": {"$sum": "$chunks"}}},
    ]))

    from . import runtime

    cfg = runtime.current()
    return {
        "generated_at": now.isoformat(),
        "window_days": days,
        "users": {"total": len(users_all), "active": active, "sessions_total": count({"kind": "session"})},
        "chats": {
            "total": count(chats_q),
            "today": count({**chats_q, "ts": {"$gte": day_start}}),
            "window": len(recent),
            "hosted": sum(1 for r in recent if r.get("mode") == "hosted"),
            "byok": sum(1 for r in recent if r.get("mode") == "byok"),
            "grounded_pct": round(100 * sum(1 for r in recent if r.get("grounded")) / n, 1),
            "abstained_pct": round(100 * sum(1 for r in recent if r.get("abstained") and not r.get("blocked")) / n, 1),
            "blocked_pct": round(100 * sum(1 for r in recent if r.get("blocked")) / n, 1),
            "errors": sum(1 for r in recent if r.get("error")),
            "latency_ms": {"p50": _pct(lat, 50), "p95": _pct(lat, 95), "avg": int(statistics.mean(lat)) if lat else None},
            "models": dict(sorted(models.items(), key=lambda kv: -kv[1])[:10]),
            "guardrails": {g["_id"]: g["n"] for g in guard},
        },
        "documents": {
            "live": live.get("docs", 0),
            "live_chunks": live.get("chunks", 0),
            "live_chars": live.get("chars", 0),
            "uploaded_total": up.get("n", 0),
            "chunked_total": up.get("chunks", 0),
            "pages_total": up.get("pages", 0),
            "rejected_total": count({"kind": "upload_rejected"}),
            "rejected_reasons": {r["_id"] or "other": r["n"] for r in rejects},
            "deleted": {(d["_id"] or "user"): {"docs": d["docs"], "chunks": d["chunks"]} for d in deletes},
            "flagged_injection": count({"kind": "upload", "warnings": "possible_prompt_injection"}),
        },
        "hosted_today": {
            "used": used("hosted_global", "all"),
            "limit": cfg.hosted.daily_global,
            "enabled": runtime.hosted_available(cfg),
        },
        "daily": daily,
    }


def _public_event(e: dict) -> dict:
    e = dict(e)
    e["id"] = str(e.pop("_id"))
    if isinstance(e.get("ts"), datetime):
        e["ts"] = e["ts"].isoformat()
    return e


def list_events(*, kind: str | None = None, user: str | None = None, q: str | None = None,
                flag: str | None = None, before: str | None = None, limit: int = 50) -> dict:
    query: dict = {}
    if kind:
        query["kind"] = kind
    if user:
        query["user"] = user[:64]
    if q:
        rx = {"$regex": re.escape(q[:100]), "$options": "i"}
        query["$or"] = [{"query": rx}, {"answer": rx}, {"filename": rx}]
    if flag in ("blocked", "abstained", "grounded", "error"):
        query[flag] = {"$nin": [None, False, ""]}
    if before:
        try:
            query["ts"] = {"$lt": datetime.fromisoformat(before)}
        except ValueError:
            pass
    limit = max(1, min(limit, 200))
    rows = [_public_event(e) for e in db.events().find(query).sort("ts", -1).limit(limit)]
    return {"events": rows, "next": rows[-1]["ts"] if len(rows) == limit else None}


def list_users(limit: int = 100) -> list[dict]:
    rows = list(db.events().aggregate([
        {"$match": {"user": {"$ne": None}}},
        {"$group": {
            "_id": "$user",
            "first_seen": {"$min": "$ts"}, "last_seen": {"$max": "$ts"},
            "chats": {"$sum": {"$cond": [{"$eq": ["$kind", "chat"]}, 1, 0]}},
            "uploads": {"$sum": {"$cond": [{"$eq": ["$kind", "upload"]}, 1, 0]}},
            "blocked": {"$sum": {"$cond": [{"$eq": ["$blocked", True]}, 1, 0]}},
            "rejected_uploads": {"$sum": {"$cond": [{"$eq": ["$kind", "upload_rejected"]}, 1, 0]}},
            "ips": {"$addToSet": "$ip"},
        }},
        {"$sort": {"last_seen": -1}}, {"$limit": max(1, min(limit, 500))},
    ]))
    live = {d["_id"]: d["n"] for d in db.documents().aggregate([{"$group": {"_id": "$user_id", "n": {"$sum": 1}}}])}
    return [{
        "user": r["_id"], "first_seen": r["first_seen"].isoformat(), "last_seen": r["last_seen"].isoformat(),
        "chats": r["chats"], "uploads": r["uploads"], "blocked": r["blocked"],
        "rejected_uploads": r["rejected_uploads"], "ips": len([i for i in r["ips"] if i]), "live_docs": live.get(r["_id"], 0),
    } for r in rows]
