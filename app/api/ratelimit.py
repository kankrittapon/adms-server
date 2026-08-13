"""In-process fixed-window rate limiting.

PromptID: ADMS-Frontend-F5-Hardening-001

Small, dependency-free limiter for the LAN-only API. Accurate because the API
runs as a single uvicorn worker. Each scope keeps a fixed-window counter keyed
by client IP:

    limit(key, scope, per_min) -> (allowed, retry_after_seconds)

Windows are evicted lazily. Thread-safe via a module lock (uvicorn may serve
requests from multiple threads).
"""

import threading
import time
from typing import Dict, Tuple

_WINDOW_SECONDS = 60.0
_lock = threading.Lock()
# scope -> { key: (window_start_epoch, count) }
_BUCKETS: Dict[str, Dict[str, Tuple[float, int]]] = {}


def _now() -> float:
    return time.monotonic()


def check_limit(key: str, scope: str, per_min: int) -> Tuple[bool, float]:
    """Returns (allowed, retry_after_seconds).

    - allowed=True: request proceeds (count incremented).
    - allowed=False: limit exceeded; retry_after is seconds until the window
      resets (from the current window start).
    """
    if per_min <= 0:
        return True, 0.0
    now = _now()
    with _lock:
        bucket = _BUCKETS.get(scope)
        if bucket is None:
            bucket = {}
            _BUCKETS[scope] = bucket
        entry = bucket.get(key)
        if entry is None or now - entry[0] >= _WINDOW_SECONDS:
            bucket[key] = (now, 1)
            _evict(now)
            return True, 0.0
        window_start, count = entry
        if count >= per_min:
            retry_after = max(1.0, _WINDOW_SECONDS - (now - window_start))
            return False, retry_after
        bucket[key] = (window_start, count + 1)
        return True, 0.0


def _evict(now: float) -> None:
    """Drops expired windows to bound memory growth."""
    for scope in list(_BUCKETS):
        bucket = _BUCKETS[scope]
        for key in list(bucket):
            if now - bucket[key][0] >= _WINDOW_SECONDS:
                del bucket[key]
        if not bucket:
            del _BUCKETS[scope]


def reset() -> None:
    """Clears all buckets (tests)."""
    with _lock:
        _BUCKETS.clear()
