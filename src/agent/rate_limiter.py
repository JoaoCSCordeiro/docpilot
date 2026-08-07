import threading
import time
from typing import Callable


class TokenBucket:
    def __init__(
        self,
        capacity: int,
        refill_period_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity deve ser positivo")

        self.capacity = capacity
        self.refill_period_seconds = refill_period_seconds
        self._clock = clock
        self._sleep = sleep
        self._tokens = float(capacity)
        self._last_refill = clock()
        self._lock = threading.Lock()

    def _refill_locked(self) -> None:
        now = self._clock()
        elapsed = now - self._last_refill
        refill_rate = self.capacity / self.refill_period_seconds
        self._tokens = min(self.capacity, self._tokens + elapsed * refill_rate)
        self._last_refill = now

    def acquire(self, tokens: float = 1.0) -> None:
        with self._lock:
            self._refill_locked()
            deficit = tokens - self._tokens
            if deficit > 0:
                refill_rate = self.capacity / self.refill_period_seconds
                self._sleep(deficit / refill_rate)
                self._refill_locked()
            self._tokens -= tokens
