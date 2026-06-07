"""User identity.

The DocLens frontend mints a lightweight bearer token (an unsigned JWT-shaped
string) whose payload carries a stable per-browser ``sub`` (the user id). We trust
and decode that ``sub`` — there are no accounts/passwords; the user id simply
scopes a person's chats and documents. Every Brain call then uses this id as the
vector ``namespace`` so one user can never retrieve another's documents.
"""
from __future__ import annotations

import base64
import json

from fastapi import HTTPException, Request


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("utf-8"))


def _sub_from_token(token: str) -> str:
    parts = token.split(".")
    if len(parts) < 2:
        return ""
    try:
        payload = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
    except Exception:  # noqa: BLE001 — malformed token → no identity
        return ""
    return str(payload.get("sub") or "").strip()


def user_id_from_request(request: Request, fallback: str | None = None) -> str:
    """Resolve the caller's user id from the bearer token's ``sub`` claim.

    Falls back to an explicit value (e.g. a form/body field) when provided, then
    raises 401 if no identity can be determined."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    if token:
        sub = _sub_from_token(token)
        if sub:
            return sub

    fallback = (fallback or "").strip()
    if fallback:
        return fallback

    raise HTTPException(status_code=401, detail="Authorization bearer token with a sub claim is required.")
