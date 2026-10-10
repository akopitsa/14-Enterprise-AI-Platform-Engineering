"""Справжній token bucket (слайд 15 каже token bucket; код на слайді 44 — це fixed window)."""
import time


class TokenBucket:
    def __init__(self):
        self._state = {}   # key -> (tokens, last_ts)

    def allow(self, key, rate_per_min, burst=None):
        cap = burst or rate_per_min
        now = time.monotonic()
        tokens, last = self._state.get(key, (float(cap), now))
        tokens = min(cap, tokens + (now - last) * rate_per_min / 60.0)
        if tokens >= 1:
            self._state[key] = (tokens - 1, now)
            return True, 0.0
        self._state[key] = (tokens, now)
        return False, (1 - tokens) * 60.0 / rate_per_min
