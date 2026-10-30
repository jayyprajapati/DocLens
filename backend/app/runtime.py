"""Runtime settings — what the admin panel controls without a redeploy.

One Mongo document (``doclens_settings`` / ``_id="runtime"``) holds the live values; env vars only
seed the defaults. Every value is validated here (DocLens owns its own invariants — the admin
panel can't push a negative quota or an unknown provider), cached for a few seconds, and read
through ``current()``.

Infrastructure secrets (Mongo URI, Brain key, the hosted Ollama key, session secret) are NOT
runtime settings: they stay in env and are never returned by the admin API.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from . import db
from .config import settings

logger = logging.getLogger("doclens.runtime")

_ID = "runtime"
_TTL_S = 10.0

AnswerStyle = Literal["concise", "balanced", "detailed"]


class Hosted(BaseModel):
    """Free mode: visitors chat without a key, on the server's Ollama Cloud key."""

    enabled: bool = False
    # gemma4:31b: best measured free Ollama Cloud model (EVALS.md) — 98% overall, ~2 s p50
    model: str = Field("gemma4:31b", min_length=1, max_length=80)
    # fallback model used when the primary errors (rate limit / outage); "" = none
    fallback_model: str = Field("gpt-oss:120b", max_length=80)
    label: str = Field("DocLens Free", max_length=40)
    daily_per_user: int = Field(40, ge=0, le=10_000)
    daily_per_ip: int = Field(100, ge=0, le=100_000)
    daily_global: int = Field(3000, ge=0, le=1_000_000)


class Byok(BaseModel):
    enabled: bool = True
    providers: list[str] = Field(default_factory=lambda: ["openai", "anthropic", "ollama_cloud"])
    suggested_models: dict[str, list[str]] = Field(default_factory=lambda: {
        "openai": ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "o4-mini"],
        "anthropic": ["claude-sonnet-4-6", "claude-haiku-4-5-20251001", "claude-opus-4-8"],
        "ollama_cloud": ["gemma4:31b", "gpt-oss:120b", "nemotron-3-super", "gpt-oss:20b"],
    })

    @field_validator("providers")
    @classmethod
    def _known(cls, v: list[str]) -> list[str]:
        from .schemas import VALID_PROVIDERS

        return [p for p in dict.fromkeys(v) if p in VALID_PROVIDERS]

    @field_validator("suggested_models")
    @classmethod
    def _trim(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        return {k[:30]: [m.strip()[:80] for m in ms if m.strip()][:20] for k, ms in list(v.items())[:10]}


class Answer(BaseModel):
    style: AnswerStyle = "balanced"
    verify: Literal["auto", "always", "off"] = settings.answer_verify if settings.answer_verify in ("auto", "always", "off") else "auto"
    temperature: float = Field(settings.answer_temperature, ge=0.0, le=1.0)
    max_tokens: int = Field(settings.answer_max_tokens, ge=300, le=6000)
    reasoning: Literal["", "off", "low", "medium", "high"] = settings.answer_reasoning if settings.answer_reasoning in ("", "off", "low", "medium", "high") else ""


class Retrieval(BaseModel):
    max_chunks: int = Field(settings.context_max_chunks, ge=2, le=16)
    score_margin: float = Field(settings.context_score_margin, ge=0.5, le=20.0)
    evidence_gate: float = Field(settings.evidence_gate_score, ge=-20.0, le=5.0)


class Uploads(BaseModel):
    enabled: bool = True
    max_mb: int = Field(settings.max_upload_mb, ge=1, le=50)
    max_pages: int = Field(200, ge=1, le=settings.hard_max_pages)
    # bounds Brain embedding CPU per upload (~120 dense pages); the server is shared
    max_chars: int = Field(300_000, ge=10_000, le=settings.hard_max_chars)
    max_docs_per_user: int = Field(40, ge=1, le=1000)
    per_10min_per_user: int = Field(settings.upload_rate_per_10min, ge=1, le=1000)
    daily_per_user: int = Field(60, ge=1, le=10_000)
    # documents are deleted (vectors + registry) this long after upload; 0 = keep forever
    expire_hours: int = Field(24, ge=0, le=24 * 365)


class Limits(BaseModel):
    chat_per_min_per_user: int = Field(settings.chat_rate_per_min, ge=1, le=10_000)
    sessions_per_hour_per_ip: int = Field(30, ge=1, le=10_000)


class Service(BaseModel):
    chat_enabled: bool = True
    # shown in the app as a banner (maintenance notice, launch message); "" = none
    banner: str = Field("", max_length=300)


class RuntimeConfig(BaseModel):
    hosted: Hosted = Field(default_factory=Hosted)
    byok: Byok = Field(default_factory=Byok)
    answer: Answer = Field(default_factory=Answer)
    retrieval: Retrieval = Field(default_factory=Retrieval)
    uploads: Uploads = Field(default_factory=Uploads)
    limits: Limits = Field(default_factory=Limits)
    service: Service = Field(default_factory=Service)


_lock = threading.Lock()
_cache: tuple[float, RuntimeConfig] | None = None


def _load() -> RuntimeConfig:
    try:
        doc = db.settings_coll().find_one({"_id": _ID}) or {}
    except Exception as exc:  # noqa: BLE001 — Mongo hiccup: keep serving on defaults/last value
        logger.warning("runtime settings unavailable, using defaults: %s", exc)
        return _cache[1] if _cache else RuntimeConfig()
    doc.pop("_id", None)
    doc.pop("updated_at", None)
    doc.pop("updated_by", None)
    try:
        return RuntimeConfig.model_validate(doc)
    except Exception as exc:  # noqa: BLE001 — a bad stored doc must never take the app down
        logger.error("stored runtime settings invalid, using defaults: %s", exc)
        return RuntimeConfig()


def current() -> RuntimeConfig:
    global _cache
    now = time.monotonic()
    c = _cache
    if c and now - c[0] < _TTL_S:
        return c[1]
    with _lock:
        if _cache and now - _cache[0] < _TTL_S:
            return _cache[1]
        cfg = _load()
        _cache = (now, cfg)
        return cfg


def update(patch: dict, actor: str = "admin") -> RuntimeConfig:
    """Deep-merge ``patch`` over the current config, validate, store. Raises ValueError."""
    global _cache
    base = current().model_dump()
    for section, values in (patch or {}).items():
        if section not in base or not isinstance(values, dict):
            raise ValueError(f"unknown settings section: {section}")
        base[section].update(values)
    cfg = RuntimeConfig.model_validate(base)  # raises on bad values
    db.settings_coll().replace_one(
        {"_id": _ID},
        {"_id": _ID, **cfg.model_dump(), "updated_at": datetime.now(timezone.utc), "updated_by": actor[:60]},
        upsert=True,
    )
    with _lock:
        _cache = (time.monotonic(), cfg)
    return cfg


def reset_cache() -> None:
    global _cache
    with _lock:
        _cache = None


def hosted_available(cfg: RuntimeConfig | None = None) -> bool:
    cfg = cfg or current()
    return cfg.hosted.enabled and bool(settings.hosted_ollama_api_key)
