from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import RLock

from fastapi import HTTPException, status

from app.config import settings

_lock = RLock()
_attempts: dict[str, deque[float]] = defaultdict(deque)


def check_auth_rate_limit(key: str) -> None:
    now = time.monotonic()
    cutoff = now - settings.auth_rate_limit_window_seconds

    with _lock:
        events = _attempts[key]
        while events and events[0] < cutoff:
            events.popleft()

        if len(events) >= settings.auth_rate_limit_attempts:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many authentication attempts. Try again later.",
            )

        events.append(now)


def clear_auth_rate_limit(key: str) -> None:
    with _lock:
        _attempts.pop(key, None)
