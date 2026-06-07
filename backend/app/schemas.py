"""Request/response models for the DocLens API."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

# BYOK providers DocLens accepts. These map 1:1 to Brain's supported providers.
VALID_PROVIDERS = {"openai", "anthropic", "ollama_cloud", "ollama_local"}


class ChatRequest(BaseModel):
    query: str
    user_id: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    provider: str = "openai"
    thread_id: Optional[str] = None
    # Optional explicit scope override (e.g. user picked one document to ask about).
    doc_ids: Optional[List[str]] = None


class ThreadPatchRequest(BaseModel):
    title: Optional[str] = None


class DeleteRequest(BaseModel):
    doc_id: str = Field(min_length=1)
    # api_key is accepted for forward-compat but unused: deletion needs no LLM.
    api_key: Optional[str] = None


class DeleteAllRequest(BaseModel):
    api_key: Optional[str] = None
