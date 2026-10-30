"""Internal admin API — called server-to-server by the Admin panel's backend, never by browsers.

Auth: ``X-Admin-Token`` must equal ``ADMIN_API_TOKEN`` (constant-time compare). With no token
configured every route 404s, as if it didn't exist. Caddy also refuses ``/internal/*`` on the
public hostname (see DEPLOYMENT.md), so the Admin backend reaches it only over the private
Docker network (``http://doclens-backend:8001``).

Exposes: live runtime settings (read/update), usage stats, the event log, per-user summaries,
the hosted key's model list and a one-shot model test. Secrets are never returned.
"""
from __future__ import annotations

import hmac
import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, ValidationError

from .. import analytics, brain_client, db, runtime
from ..config import settings
from ..services import documents as doc_service

def _require_admin(x_admin_token: Optional[str] = Header(None)) -> None:
    expected = settings.admin_api_token
    if not expected:
        raise HTTPException(status_code=404, detail="Not Found")
    if not x_admin_token or not hmac.compare_digest(x_admin_token.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid admin token")


router = APIRouter(prefix="/internal/admin", dependencies=[Depends(_require_admin)])


class ConfigPatch(BaseModel):
    patch: dict[str, Any] = Field(default_factory=dict)
    actor: str = Field("admin", max_length=60)


class ModelTest(BaseModel):
    model: str = Field(min_length=1, max_length=80)


def _config_payload() -> dict:
    stored = db.settings_coll().find_one({"_id": "runtime"}, {"updated_at": 1, "updated_by": 1}) or {}
    return {
        "config": runtime.current().model_dump(),
        "meta": {
            "hosted_key_configured": bool(settings.hosted_ollama_api_key),
            "session_signing": bool(settings.session_secret),
            "updated_at": stored["updated_at"].isoformat() if stored.get("updated_at") else None,
            "updated_by": stored.get("updated_by"),
            "hard_limits": {
                "max_pages": settings.hard_max_pages,
                "max_chars": settings.hard_max_chars,
                "extract_timeout_s": settings.extract_timeout_s,
                "extract_mem_mb": settings.extract_mem_mb,
                "extract_concurrency": settings.extract_concurrency,
            },
            "events_retention_days": settings.events_retention_days,
        },
    }


@router.get("/config")
def get_config():
    runtime.reset_cache()
    return _config_payload()


@router.put("/config")
def put_config(body: ConfigPatch):
    try:
        runtime.update(body.patch, actor=body.actor)
    except ValidationError as exc:
        errs = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:8]]
        raise HTTPException(status_code=422, detail="; ".join(errs)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    analytics.record("config_change", actor=body.actor, sections=sorted(body.patch.keys()))
    return _config_payload()


@router.get("/stats")
def get_stats(days: int = 30):
    return analytics.stats(days=max(1, min(days, 180)))


@router.get("/events")
def get_events(kind: Optional[str] = None, user: Optional[str] = None, q: Optional[str] = None,
               flag: Optional[str] = None, before: Optional[str] = None, limit: int = 50):
    return analytics.list_events(kind=kind, user=user, q=q, flag=flag, before=before, limit=limit)


@router.get("/users")
def get_users(limit: int = 100):
    return {"users": analytics.list_users(limit=limit)}


@router.get("/models")
def hosted_models():
    """Models the hosted Ollama Cloud key can use (for the model picker)."""
    if not settings.hosted_ollama_api_key:
        return {"models": [], "error": "HOSTED_OLLAMA_API_KEY is not set on the DocLens server."}
    try:
        resp = httpx.get("https://ollama.com/api/tags", headers={"Authorization": f"Bearer {settings.hosted_ollama_api_key}"}, timeout=10)
        resp.raise_for_status()
        rows = resp.json().get("models", [])
    except Exception as exc:  # noqa: BLE001
        return {"models": [], "error": f"Could not list models: {type(exc).__name__}"}
    rows.sort(key=lambda m: m.get("modified_at", ""), reverse=True)
    return {"models": [{"name": m.get("name") or m.get("model"), "modified_at": (m.get("modified_at") or "")[:10]} for m in rows if m.get("name") or m.get("model")]}


@router.post("/test-model")
def test_model(body: ModelTest):
    """One tiny grounded call on the hosted key: does this model answer, follow the format, and
    how fast? Run it before switching the hosted model."""
    if not settings.hosted_ollama_api_key:
        raise HTTPException(status_code=400, detail="HOSTED_OLLAMA_API_KEY is not set on the DocLens server.")
    from ..prompts import answer_system, build_user_prompt

    chunks = [{"doc_id": "t", "heading": "Refunds", "text": "Refunds are issued within 14 days of receiving the returned item. Opened software cannot be refunded."}]
    prompt, _ = build_user_prompt("How long do refunds take, and can I return opened software?", chunks, {"t": "policy.pdf"}, [])
    llm = {"provider": "ollama_cloud", "api_key": settings.hosted_ollama_api_key, "model": body.model}
    t0 = time.perf_counter()
    try:
        out = brain_client.generate(system=answer_system(runtime.current().answer.style), prompt=prompt, llm=llm, max_tokens=800, temperature=0.1)
    except brain_client.BrainError as exc:
        return {"ok": False, "model": body.model, "error": exc.detail[:300], "ms": round((time.perf_counter() - t0) * 1000)}
    text = out.get("text") or ""
    return {
        "ok": "<answer>" in text and "14 days" in text,
        "model": body.model,
        "ms": round((time.perf_counter() - t0) * 1000),
        "followed_format": "<answer>" in text,
        "reply": text[:1500],
    }


@router.post("/sweep")
def sweep_now():
    """Run the document-expiry sweep immediately (it also runs every 10 minutes)."""
    return {"expired": doc_service.sweep_expired()}
