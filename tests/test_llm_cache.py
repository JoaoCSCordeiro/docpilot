from pathlib import Path

import fakeredis
import pytest
import redis

from src.agent import llm_cache
from src.agent.llm_cache import (
    REDIS_KEY_PREFIX,
    RedisResponseCache,
    SQLiteResponseCache,
    cache_key,
    get_response_cache,
)
from src.config import settings

MODEL = "openai/gpt-oss-120b"


class BrokenRedis:
    def get(self, key: str) -> None:
        raise redis.ConnectionError("Redis em baixo")

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        raise redis.ConnectionError("Redis em baixo")


@pytest.fixture
def sqlite_cache(tmp_path: Path) -> SQLiteResponseCache:
    return SQLiteResponseCache(tmp_path / "cache.db")


@pytest.fixture(autouse=True)
def fresh_cache_factory():
    get_response_cache.cache_clear()
    yield
    get_response_cache.cache_clear()


def test_get_returns_none_when_not_cached(sqlite_cache: SQLiteResponseCache) -> None:
    assert sqlite_cache.get(MODEL, "pergunta nunca vista") is None


def test_set_and_get_response(sqlite_cache: SQLiteResponseCache) -> None:
    sqlite_cache.set(MODEL, "qual e a capital de Portugal?", "Lisboa")

    assert sqlite_cache.get(MODEL, "qual e a capital de Portugal?") == "Lisboa"


def test_different_prompts_do_not_collide(sqlite_cache: SQLiteResponseCache) -> None:
    sqlite_cache.set(MODEL, "prompt a", "resposta a")
    sqlite_cache.set(MODEL, "prompt b", "resposta b")

    assert sqlite_cache.get(MODEL, "prompt a") == "resposta a"
    assert sqlite_cache.get(MODEL, "prompt b") == "resposta b"


def test_storing_again_for_same_prompt_overwrites_previous_response(
    sqlite_cache: SQLiteResponseCache,
) -> None:
    sqlite_cache.set(MODEL, "prompt", "resposta antiga")
    sqlite_cache.set(MODEL, "prompt", "resposta nova")

    assert sqlite_cache.get(MODEL, "prompt") == "resposta nova"


def test_same_prompt_for_different_models_is_cached_separately(
    sqlite_cache: SQLiteResponseCache,
) -> None:
    sqlite_cache.set("gerador", "mesmo prompt", "resposta do gerador")

    assert sqlite_cache.get("juiz", "mesmo prompt") is None
    sqlite_cache.set("juiz", "mesmo prompt", "veredicto do juiz")
    assert sqlite_cache.get("gerador", "mesmo prompt") == "resposta do gerador"


def test_redis_cache_is_shared_by_two_clients_of_the_same_server() -> None:
    server = fakeredis.FakeServer()
    replica_a = RedisResponseCache(fakeredis.FakeRedis(server=server, decode_responses=True))
    replica_b = RedisResponseCache(fakeredis.FakeRedis(server=server, decode_responses=True))

    replica_a.set(MODEL, "prompt", "resposta")

    assert replica_b.get(MODEL, "prompt") == "resposta"


def test_redis_cache_uses_the_same_key_hash_as_sqlite() -> None:
    client = fakeredis.FakeRedis(decode_responses=True)

    RedisResponseCache(client).set(MODEL, "prompt", "resposta")

    assert client.get(REDIS_KEY_PREFIX + cache_key(MODEL, "prompt")) == "resposta"


def test_redis_cache_applies_the_ttl() -> None:
    client = fakeredis.FakeRedis(decode_responses=True)

    RedisResponseCache(client, ttl_seconds=3600).set(MODEL, "prompt", "resposta")

    assert 0 < client.ttl(REDIS_KEY_PREFIX + cache_key(MODEL, "prompt")) <= 3600


def test_redis_cache_without_ttl_does_not_expire() -> None:
    client = fakeredis.FakeRedis(decode_responses=True)

    RedisResponseCache(client, ttl_seconds=0).set(MODEL, "prompt", "resposta")

    assert client.ttl(REDIS_KEY_PREFIX + cache_key(MODEL, "prompt")) == -1


def test_redis_errors_fall_back_to_sqlite(sqlite_cache: SQLiteResponseCache) -> None:
    cache = RedisResponseCache(BrokenRedis(), fallback=sqlite_cache)

    cache.set(MODEL, "prompt", "resposta")

    assert sqlite_cache.get(MODEL, "prompt") == "resposta"
    assert cache.get(MODEL, "prompt") == "resposta"


def test_redis_errors_without_fallback_are_a_cache_miss() -> None:
    cache = RedisResponseCache(BrokenRedis())

    cache.set(MODEL, "prompt", "resposta")

    assert cache.get(MODEL, "prompt") is None


def test_factory_defaults_to_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_cache_backend", "sqlite")

    assert isinstance(get_response_cache(), SQLiteResponseCache)


def test_factory_uses_redis_when_configured_and_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_cache_backend", "redis")
    monkeypatch.setattr(llm_cache, "get_redis_client", lambda: fakeredis.FakeRedis())

    assert isinstance(get_response_cache(), RedisResponseCache)


def test_factory_falls_back_to_sqlite_when_redis_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_cache_backend", "redis")
    monkeypatch.setattr(llm_cache, "get_redis_client", lambda: None)

    assert isinstance(get_response_cache(), SQLiteResponseCache)
