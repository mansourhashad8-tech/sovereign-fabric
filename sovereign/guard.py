"""API guards: optional key authentication, rate limiting, body limits, headers.

The key is opt-in. If SOVEREIGN_API_KEY is unset, mutating endpoints stay open
for local development. When it is set, every non-GET request must carry
X-API-Key; the comparison is constant-time. The rate limiter is a per-client
sliding window; it is not a distributed limiter.
"""

from __future__ import annotations

import hmac
import os
import threading
import time
from collections import deque
from dataclasses import dataclass

API_KEY_ENV = "SOVEREIGN_API_KEY"
RATE_LIMIT_ENV = "SOVEREIGN_RATE_LIMIT"
RATE_WINDOW_ENV = "SOVEREIGN_RATE_WINDOW"
MAX_BODY_ENV = "SOVEREIGN_MAX_BODY"
DEFAULT_RATE_LIMIT = 600
DEFAULT_RATE_WINDOW = 60.0
DEFAULT_MAX_BODY = 2_000_000


@dataclass(frozen=True)
class Decision:
    allowed: bool
    remaining: int
    retry_after: int = 0


class ApiKey:
    def __init__(self, key: str | None = None) -> None:
        self.key = key if key is not None else os.environ.get(API_KEY_ENV, "")

    @property
    def enabled(self) -> bool:
        return bool(self.key)

    def allows(self, provided: str | None) -> bool:
        if not self.enabled:
            return True
        return bool(provided) and hmac.compare_digest(provided, self.key)


class RateLimiter:
    def __init__(self, limit: int | None = None, window_s: float | None = None) -> None:
        self.limit = limit if limit is not None else int(
            os.environ.get(RATE_LIMIT_ENV, DEFAULT_RATE_LIMIT)
        )
        self.window_s = window_s if window_s is not None else float(
            os.environ.get(RATE_WINDOW_ENV, DEFAULT_RATE_WINDOW)
        )
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, now: float | None = None) -> Decision:
        current = time.monotonic() if now is None else now
        cutoff = current - self.window_s
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.limit:
                retry = max(1, int(hits[0] + self.window_s - current) + 1)
                return Decision(False, 0, retry)
            hits.append(current)
            if len(self._hits) > 10_000:
                self._hits = {k: v for k, v in self._hits.items() if v}
            return Decision(True, self.limit - len(hits))


def max_body_bytes() -> int:
    return int(os.environ.get(MAX_BODY_ENV, DEFAULT_MAX_BODY))


def security_headers() -> dict[str, str]:
    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Content-Security-Policy": (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
            "form-action 'self'"
        ),
    }
