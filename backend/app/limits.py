"""Tiny in-process sliding-window rate limiter (per user id).

Single-process only — fine for the one backend container DocLens runs today; swap for Redis
if the backend is ever scaled out."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

_lock = threading.Lock()
_hits: dict[tuple[str, str], deque] = defaultdict(deque)


def allow(bucket: str, user_id: str, limit: int, window_s: float) -> bool:
    """Record a hit and return False when ``user_id`` exceeded ``limit`` in the window."""
    if limit <= 0:
        return True
    now = time.monotonic()
    with _lock:
        q = _hits[(bucket, user_id)]
        while q and now - q[0] > window_s:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        if len(_hits) > _MAX_KEYS:
            _purge(now)
        return True


_MAX_KEYS = 20_000


def _purge(now: float) -> None:
    """Drop keys with no hits in the last hour so a flood of distinct ids can't grow memory."""
    for k in [k for k, q in _hits.items() if not q or now - q[-1] > 3600]:
        del _hits[k]
