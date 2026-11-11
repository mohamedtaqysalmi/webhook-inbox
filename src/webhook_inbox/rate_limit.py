"""Simple in-memory sliding-window rate limiter.

Fine for a single-process self-hosted deploy. Limits are per client IP and reset
as old timestamps fall out of the window. Not shared across workers.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable


class RateLimiter:
    def __init__(self, limit_per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._limit = limit_per_minute
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._limit > 0

    def allow(self, key: str) -> bool:
        if not self.enabled:
            return True
        now = self._clock()
        window_start = now - 60.0
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] < window_start:
                bucket.popleft()
            if len(bucket) >= self._limit:
                return False
            bucket.append(now)
            return True
