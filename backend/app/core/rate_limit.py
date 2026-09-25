"""Sliding-window rate limiting (TRD v4.1 §7).

Auth-sensitive target: 10 requests/min/IP. General target: 120/min.
This in-process limiter is the documented development/test implementation;
the production backend is Redis-based (tracked gap, see README status board).
"""
import time
from collections import defaultdict, deque

from fastapi.responses import JSONResponse

from .errors import error_response

WINDOW_SECONDS = 60


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque] = defaultdict(deque)

    def hit(self, key: str, limit: int, window: int = WINDOW_SECONDS) -> bool:
        now = time.monotonic()
        dq = self._events[key]
        while dq and now - dq[0] >= window:
            dq.popleft()
        if len(dq) >= limit:
            dq.append(now)  # keep sliding the window even when rejected
            return False
        dq.append(now)
        return True

    def clear(self) -> None:
        self._events.clear()


limiter = SlidingWindowLimiter()


def rate_limited_response() -> JSONResponse:
    return error_response(429, "RATE_LIMITED", "Too many requests; retry later")
