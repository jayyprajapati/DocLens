"""User identity: server-signed anonymous sessions.

There are no accounts. A browser gets a random user id from ``POST /session`` as an HMAC-signed
token (``dl1.<payload>.<sig>``) and sends it as ``Authorization: Bearer``. Only tokens this server
signed are accepted, so a client can't claim someone else's id or mint unlimited identities to
dodge quotas (session minting itself is rate-limited per IP). The id scopes a person's chats and
documents and is Brain's vector ``namespace``.

Older browsers hold an *unsigned* token they minted themselves; ``/session`` upgrades it once
(same id, now signed) so their documents survive the switch.

Dev convenience: with no ``SESSION_SECRET`` in a dev environment, unsigned tokens (and an explicit
``user_id`` field) are still accepted so local evals keep working. Production refuses to serve
without a secret.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
import uuid

from fastapi import HTTPException, Request

from .config import settings

_PREFIX = "dl1"
_MAX_AGE_S = 400 * 86400
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(value: str) -> bytes:
    return base64.urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode())


def _sig(body: str) -> str:
    return _b64e(hmac.new(settings.session_secret.encode(), body.encode(), hashlib.sha256).digest())


def signing_enabled() -> bool:
    return bool(settings.session_secret)


def mint(sub: str | None = None) -> tuple[str, str]:
    """Return (token, user_id) for ``sub`` (or a fresh random id)."""
    sub = sub or str(uuid.uuid4())
    body = _b64e(json.dumps({"sub": sub, "iat": int(time.time())}, separators=(",", ":")).encode())
    return f"{_PREFIX}.{body}.{_sig(body)}", sub


def verify(token: str) -> str:
    """The ``sub`` of a token this server signed, or "" (bad signature, malformed, too old)."""
    parts = (token or "").split(".")
    if len(parts) != 3 or parts[0] != _PREFIX or not signing_enabled():
        return ""
    if not hmac.compare_digest(parts[2], _sig(parts[1])):
        return ""
    try:
        payload = json.loads(_b64d(parts[1]))
    except Exception:  # noqa: BLE001
        return ""
    if int(payload.get("iat", 0)) < time.time() - _MAX_AGE_S:
        return ""
    return str(payload.get("sub") or "")


def legacy_sub(token: str) -> str:
    """The ``sub`` of an old unsigned browser token, only if it is a well-formed UUID."""
    parts = (token or "").split(".")
    if len(parts) < 2 or parts[0] == _PREFIX:
        return ""
    try:
        sub = str(json.loads(_b64d(parts[1])).get("sub") or "").strip().lower()
    except Exception:  # noqa: BLE001
        return ""
    return sub if _UUID.match(sub) else ""


def bearer(request: Request) -> str:
    h = request.headers.get("Authorization", "")
    return h[7:].strip() if h.startswith("Bearer ") else ""


def user_id_from_request(request: Request, fallback: str | None = None) -> str:
    """Resolve the caller's user id. 401 if there's no valid session."""
    token = bearer(request)
    if signing_enabled():
        sub = verify(token)
        if sub:
            return sub
        raise HTTPException(status_code=401, detail="Your session expired. Reload the page to start a new one.")
    if not settings.is_dev:
        raise HTTPException(status_code=503, detail="Server misconfigured: SESSION_SECRET is not set.")
    # dev only: trust unsigned tokens / explicit ids (local evals and tests)
    sub = legacy_sub(token) or _unsigned_sub(token) or (fallback or "").strip()
    if sub:
        return sub
    raise HTTPException(status_code=401, detail="Authorization bearer token with a sub claim is required.")


def _unsigned_sub(token: str) -> str:
    parts = (token or "").split(".")
    if len(parts) < 2:
        return ""
    try:
        return str(json.loads(_b64d(parts[1])).get("sub") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def client_ip(request: Request) -> str:
    """The real client IP. Caddy (the only thing in front of us) replaces X-Forwarded-For for
    untrusted clients; take the right-most hop so a spoofed left-most entry is never used."""
    xff = request.headers.get("X-Forwarded-For", "")
    hops = [h.strip() for h in xff.split(",") if h.strip()]
    if hops:
        return hops[-1][:64]
    return (request.client.host if request.client else "") or "unknown"


def ip_hash(ip: str) -> str:
    """Stable pseudonymous IP id for quotas/analytics — raw IPs are never stored."""
    key = (settings.session_secret or "doclens-dev").encode()
    return hmac.new(key, ("ip:" + ip).encode(), hashlib.sha256).hexdigest()[:16]
