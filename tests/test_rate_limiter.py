import pytest

from src.agent.rate_limiter import TokenBucket


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
