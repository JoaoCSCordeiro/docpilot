import logging
import threading
import time
from typing import Callable, Protocol

import redis

logger = logging.getLogger(__name__)


class RateLimiter(Protocol):
    def acquire(self, tokens: float = 1.0) -> None: ...


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


# Ler, reabastecer e descontar numa so operacao: o Redis corre o script de forma
# atomica, por isso duas replicas nunca gastam o mesmo token. O relogio e o do Redis
# (TIME), nao o de cada replica, para os pods nao dependerem de relogios sincronizados.
# Devolve o tempo de espera como string porque um numero Lua seria truncado para inteiro.
_ACQUIRE_SCRIPT = """
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local requested = tonumber(ARGV[3])
local redis_time = redis.call('TIME')
local now = tonumber(redis_time[1]) + tonumber(redis_time[2]) / 1000000
local state = redis.call('HMGET', KEYS[1], 'tokens', 'timestamp')
local tokens = tonumber(state[1]) or capacity
local timestamp = tonumber(state[2]) or now
tokens = math.min(capacity, tokens + math.max(0, now - timestamp) * refill_rate)
local wait = 0
if tokens >= requested then
  tokens = tokens - requested
else
  wait = (requested - tokens) / refill_rate
end
redis.call('HSET', KEYS[1], 'tokens', tostring(tokens), 'timestamp', tostring(now))
redis.call('EXPIRE', KEYS[1], math.ceil(capacity / refill_rate) * 2)
return tostring(wait)
"""


class RedisTokenBucket:
    def __init__(
        self,
        client: redis.Redis,
        key: str,
        capacity: int,
        refill_period_seconds: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
        fallback: RateLimiter | None = None,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity deve ser positivo")

        self.capacity = capacity
        self.refill_period_seconds = refill_period_seconds
        self._key = key
        self._sleep = sleep
        self._fallback = fallback
        self._script = client.register_script(_ACQUIRE_SCRIPT)

    def try_acquire(self, tokens: float = 1.0) -> float:
        # 0.0 = tokens descontados; > 0 = segundos a esperar, sem nada descontado.
        refill_rate = self.capacity / self.refill_period_seconds
        return float(self._script(keys=[self._key], args=[self.capacity, refill_rate, tokens]))

    def acquire(self, tokens: float = 1.0) -> None:
        # Ao contrario do TokenBucket local, nao se reserva o token durante a espera:
        # outra replica pode apanha-lo primeiro, e entao volta-se a esperar.
        while True:
            try:
                wait_seconds = self.try_acquire(tokens)
            except redis.RedisError as error:
                if self._fallback is None:
                    raise
                logger.warning("Rate limiter Redis falhou (%s); a usar o limite local", error)
                self._fallback.acquire(tokens)
                return
            if wait_seconds <= 0:
                return
            self._sleep(wait_seconds)
