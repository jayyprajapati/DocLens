"""Request/response models for the DocLens API. Every free-form field is length-capped so a
client can't make the server parse or store unbounded input."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from .config import settings

# BYOK providers DocLens accepts. These map 1:1 to Brain's supported providers.
# ``ollama_local`` (a self-hosted Ollama with no key) only makes sense on a developer machine.
VALID_PROVIDERS = {"openai", "anthropic", "ollama_cloud", "ollama_local"}


def public_providers() -> set[str]:
    return VALID_PROVIDERS if settings.is_dev else VALID_PROVIDERS - {"ollama_local"}


class ChatRequest(BaseModel):
    query: str = Field(max_length=20_000)
    api_key: Optional[str] = Field(None, max_length=400)
    model: Optional[str] = Field(None, max_length=100)
    # "hosted" = free mode on the server's key; otherwise a BYOK provider
    provider: str = Field("openai", max_length=30)
    thread_id: Optional[str] = Field(None, max_length=64)
    # Optional explicit scope override (e.g. user picked one document to ask about).
    doc_ids: Optional[List[str]] = Field(None, max_length=50)
    # accepted for old clients; identity always comes from the session token
    user_id: Optional[str] = Field(None, max_length=64)


class SessionRequest(BaseModel):
    # an old unsigned browser token to upgrade (same user id, now signed)
    legacy_token: Optional[str] = Field(None, max_length=2000)


class ThreadPatchRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=200)


class DeleteRequest(BaseModel):
    doc_id: str = Field(min_length=1, max_length=64)
    # api_key is accepted for forward-compat but unused: deletion needs no LLM.
    api_key: Optional[str] = Field(None, max_length=400)


class DeleteAllRequest(BaseModel):
    api_key: Optional[str] = Field(None, max_length=400)
