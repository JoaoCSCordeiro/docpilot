import threading
import time

import fakeredis
import pytest
import redis

from src.agent.rate_limiter import RedisTokenBucket, TokenBucket


def test_acquire_does_not_sleep_while_tokens_are_available() -> None:
    sleeps: list[float] = []
    bucket = TokenBucket(
        capacity=2, refill_period_seconds=60.0, clock=lambda: 0.0, sleep=sleeps.append
    )

    bucket.acquire()
    bucket.acquire()

    assert sleeps == []


def test_acquire_sleeps_for_the_time_needed_to_refill_one_token() -> None:
    time_value = [0.0]
    sleeps: list[float] = []

    def clock() -> float:
        return time_value[0]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        time_value[0] += seconds

    bucket = TokenBucket(capacity=1, refill_period_seconds=60.0, clock=clock, sleep=sleep)

    bucket.acquire()
    bucket.acquire()

    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(60.0)


def test_capacity_must_be_positive() -> None:
    with pytest.raises(ValueError):
        TokenBucket(capacity=0)


def test_tokens_refill_over_time_without_exceeding_capacity() -> None:
    time_value = [0.0]
    sleeps: list[float] = []

    def clock() -> float:
        return time_value[0]

    bucket = TokenBucket(capacity=3, refill_period_seconds=60.0, clock=clock, sleep=sleeps.append)

    bucket.acquire(3)
    time_value[0] = 60.0
    bucket.acquire(3)

    assert sleeps == []


def _redis_bucket(
    client: fakeredis.FakeRedis, capacity: int, refill_period_seconds: float = 3600.0, **kwargs
) -> RedisTokenBucket:
    return RedisTokenBucket(
        client,
        "test:ratelimit",
        capacity=capacity,
        refill_period_seconds=refill_period_seconds,
        **kwargs,
    )


def test_redis_bucket_grants_up_to_capacity_then_asks_to_wait() -> None:
    bucket = _redis_bucket(fakeredis.FakeRedis(), capacity=2)

    assert bucket.try_acquire() == 0.0
    assert bucket.try_acquire() == 0.0
    assert bucket.try_acquire() == pytest.approx(1800.0, rel=0.01)


def test_two_replicas_share_one_redis_bucket_under_concurrency() -> None:
    # Duas "replicas" (clientes distintos do mesmo servidor), 10 threads cada, todas a
    # tentar ao mesmo tempo: o script atomico tem de conceder exatamente a capacidade.
    server = fakeredis.FakeServer()
    replicas = [_redis_bucket(fakeredis.FakeRedis(server=server), capacity=5) for _ in range(2)]
    start = threading.Barrier(20)
    granted: list[bool] = []
    granted_lock = threading.Lock()

    def worker(bucket: RedisTokenBucket) -> None:
        start.wait()
        result = bucket.try_acquire() == 0.0
        with granted_lock:
            granted.append(result)

    threads = [threading.Thread(target=worker, args=(replicas[index % 2],)) for index in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(granted) == 5
    assert len(granted) == 20


def test_redis_bucket_acquire_sleeps_until_a_token_refills() -> None:
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        time.sleep(seconds)

    bucket = _redis_bucket(
        fakeredis.FakeRedis(), capacity=1, refill_period_seconds=0.2, sleep=sleep
    )

    bucket.acquire()
    bucket.acquire()

    assert len(sleeps) >= 1
    assert sum(sleeps) == pytest.approx(0.2, abs=0.1)


def test_redis_bucket_falls_back_to_local_bucket_when_redis_fails() -> None:
    fallback_calls: list[float] = []
    fallback = type(
        "FakeBucket", (), {"acquire": lambda self, tokens=1.0: fallback_calls.append(tokens)}
    )()
    server = fakeredis.FakeServer()
    bucket = _redis_bucket(fakeredis.FakeRedis(server=server), capacity=1, fallback=fallback)
    server.connected = False

    bucket.acquire()

    assert fallback_calls == [1.0]


def test_redis_bucket_without_fallback_raises_when_redis_fails() -> None:
    server = fakeredis.FakeServer()
    bucket = _redis_bucket(fakeredis.FakeRedis(server=server), capacity=1)
    server.connected = False

    with pytest.raises(redis.ConnectionError):
        bucket.acquire()


def test_redis_bucket_capacity_must_be_positive() -> None:
    with pytest.raises(ValueError):
        _redis_bucket(fakeredis.FakeRedis(), capacity=0)
