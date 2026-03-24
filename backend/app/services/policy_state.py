import threading
import time


FREE_DOC_LIMIT = 1
FREE_QUERY_LIMIT = 2
BYOK_DOC_LIMIT = 5


_state_lock = threading.Lock()

user_usage = {}
user_docs = {}


def _normalize_api_key(api_key):
    return (api_key or "").strip()


def _has_api_key(api_key):
    return bool(_normalize_api_key(api_key))


def _ensure_user_usage(user_id):
    usage = user_usage.get(user_id)
    if usage is None:
        usage = {"docs": 0, "queries": 0}
        user_usage[user_id] = usage
    return usage


def _ensure_user_docs(user_id):
    docs = user_docs.get(user_id)
    if docs is None:
        docs = []
        user_docs[user_id] = docs
    return docs


def _sync_doc_count(user_id):
    usage = _ensure_user_usage(user_id)
    docs = _ensure_user_docs(user_id)
    usage["docs"] = len(docs)


def get_limits(api_key=None):
    if _has_api_key(api_key):
        return {"docs": BYOK_DOC_LIMIT, "queries": None}
    return {"docs": FREE_DOC_LIMIT, "queries": FREE_QUERY_LIMIT}


def get_usage(user_id):
    with _state_lock:
        usage = _ensure_user_usage(user_id)
        return {"docs": usage["docs"], "queries": usage["queries"]}


def get_usage_payload(user_id, api_key=None):
    limits = get_limits(api_key)
    usage = get_usage(user_id)
    return {
        "docs": usage["docs"],
        "queries": usage["queries"],
        "limits": {
            "docs": limits["docs"],
            "queries": limits["queries"],
        },
    }


def can_ingest(user_id, api_key=None):
    limits = get_limits(api_key)
    usage = get_usage(user_id)

    max_docs = limits["docs"]
    if max_docs is not None and usage["docs"] >= max_docs:
        return False

    return True


def can_query(user_id, api_key=None):
    limits = get_limits(api_key)
    usage = get_usage(user_id)

    max_queries = limits["queries"]
    if max_queries is not None and usage["queries"] >= max_queries:
        return False

    return True


def record_query(user_id):
    with _state_lock:
        usage = _ensure_user_usage(user_id)
        usage["queries"] += 1


def register_document(user_id, doc_id, filename=None, timestamp=None):
    if not doc_id:
        return

    recorded_at = timestamp if timestamp is not None else time.time()
    normalized_filename = (filename or "").strip()

    with _state_lock:
        docs = _ensure_user_docs(user_id)
        updated = False
        for entry in docs:
            if entry.get("doc_id") == doc_id:
                entry["filename"] = normalized_filename
                entry["timestamp"] = float(recorded_at)
                updated = True
                break

        if not updated:
            docs.append(
                {
                    "doc_id": doc_id,
                    "filename": normalized_filename,
                    "timestamp": float(recorded_at),
                }
            )
        _sync_doc_count(user_id)


def remove_document(user_id, doc_id):
    with _state_lock:
        docs = _ensure_user_docs(user_id)
        user_docs[user_id] = [entry for entry in docs if entry.get("doc_id") != doc_id]
        _sync_doc_count(user_id)


def remove_all_documents(user_id):
    with _state_lock:
        user_docs[user_id] = []
        _sync_doc_count(user_id)


def get_expired_documents(max_age_seconds):
    expired = []
    cutoff_ts = time.time() - max_age_seconds

    with _state_lock:
        for user_id, docs in user_docs.items():
            for entry in docs:
                ts = entry.get("timestamp")
                doc_id = entry.get("doc_id")
                if ts is None or not doc_id:
                    continue
                if float(ts) <= cutoff_ts:
                    expired.append({"user_id": user_id, "doc_id": doc_id})

    return expired
