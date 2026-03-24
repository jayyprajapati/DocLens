import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path


REGISTRY_PATH = Path(__file__).resolve().parent.parent / "data" / "document_registry.json"

_registry_lock = threading.Lock()


def _ensure_registry_file():
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not REGISTRY_PATH.exists():
        REGISTRY_PATH.write_text(json.dumps({"users": {}}, indent=2), encoding="utf-8")


def _read_registry():
    _ensure_registry_file()
    raw_content = REGISTRY_PATH.read_text(encoding="utf-8").strip()
    if not raw_content:
        return {"users": {}}

    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError:
        return {"users": {}}

    users = parsed.get("users")
    if not isinstance(users, dict):
        return {"users": {}}

    return {"users": users}


def _write_registry(data):
    REGISTRY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def register_document(user_id, doc_id):
    now_iso = datetime.now(timezone.utc).isoformat()

    with _registry_lock:
        registry = _read_registry()
        user_docs = registry["users"].setdefault(user_id, {})
        user_docs[doc_id] = {"uploaded_at": now_iso}
        _write_registry(registry)


def remove_document(user_id, doc_id):
    with _registry_lock:
        registry = _read_registry()
        user_docs = registry["users"].get(user_id, {})
        user_docs.pop(doc_id, None)
        if not user_docs and user_id in registry["users"]:
            registry["users"].pop(user_id, None)
        _write_registry(registry)


def remove_all_documents(user_id):
    with _registry_lock:
        registry = _read_registry()
        registry["users"].pop(user_id, None)
        _write_registry(registry)


def list_expired_documents(max_age_hours=24):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    expired = []

    with _registry_lock:
        registry = _read_registry()
        users = registry.get("users", {})

        for user_id, docs in users.items():
            if not isinstance(docs, dict):
                continue

            for doc_id, meta in docs.items():
                uploaded_at_raw = (meta or {}).get("uploaded_at")
                if not uploaded_at_raw:
                    continue

                try:
                    uploaded_at = datetime.fromisoformat(uploaded_at_raw)
                except ValueError:
                    continue

                if uploaded_at.tzinfo is None:
                    uploaded_at = uploaded_at.replace(tzinfo=timezone.utc)

                if uploaded_at <= cutoff:
                    expired.append({"user_id": user_id, "doc_id": doc_id})

    return expired
