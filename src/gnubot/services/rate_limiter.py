"""In-memory rate limiting (sliding window per Discord user)."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    """
    Simple sliding-window limiter keyed by arbitrary string (e.g. Discord user id).

    Not distributed-safe; sufficient for a single bot process.
    """

    max_events: int
    window_seconds: float
    _buckets: dict[str, deque[float]] = field(default_factory=dict)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self._buckets.setdefault(key, deque())
        cutoff = now - self.window_seconds
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= self.max_events:
            return False
        q.append(now)
        return True
