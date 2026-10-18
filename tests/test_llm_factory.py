import fakeredis
import pytest

from src.agent import llm as llm_module
from src.agent.llm import get_llm, get_shared_rate_limiter
from src.agent.rate_limiter import RedisTokenBucket, TokenBucket
from src.config import settings


@pytest.fixture(autouse=True)
def fake_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "groq_api_key", "gsk-test-not-a-real-key")


def test_get_llm_defaults_to_the_configured_generator_model() -> None:
    assert get_llm().model_name == settings.groq_model


def test_get_llm_accepts_another_model_and_extra_request_options() -> None:
    llm = get_llm(model="qwen/qwen3.8-27b", max_tokens=256, model_kwargs={"seed": 1})

    assert llm.model_name == "qwen/qwen3.8-27b"
    assert llm._chat_model.max_tokens == 256
    assert llm._chat_model.model_kwargs == {"seed": 1}


def test_generator_and_judge_share_one_rate_limiter_per_process() -> None:
    generator = get_llm()
    judge = get_llm(model="qwen/qwen3.8-27b")

    assert generator._rate_limiter is judge._rate_limiter is get_shared_rate_limiter()


def test_call_count_ignores_cache_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    store: dict = {}
    monkeypatch.setattr(
        llm_module, "get_cached_response", lambda model, prompt: store.get((model, prompt))
    )
    monkeypatch.setattr(
        llm_module,
        "store_response",
        lambda model, prompt, response: store.__setitem__((model, prompt), response),
    )
    monkeypatch.setattr(llm_module, "log_usage", lambda **kwargs: None)
    llm = get_llm()
    fake_message = type("FakeMessage", (), {"content": "ok", "usage_metadata": {}})()
    monkeypatch.setattr(type(llm._chat_model), "invoke", lambda self, prompt: fake_message)

    llm.invoke("prompt")
    llm.invoke("prompt")

    assert llm.call_count == 1


def test_responses_report_tokens_on_a_miss_and_zero_tokens_on_a_hit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store: dict = {}
    monkeypatch.setattr(
        llm_module, "get_cached_response", lambda model, prompt: store.get((model, prompt))
    )
    monkeypatch.setattr(
        llm_module,
        "store_response",
        lambda model, prompt, response: store.__setitem__((model, prompt), response),
    )
    monkeypatch.setattr(llm_module, "log_usage", lambda **kwargs: None)
    llm = get_llm()
    fake_message = type(
        "FakeMessage",
        (),
        {"content": "ok", "usage_metadata": {"input_tokens": 120, "output_tokens": 30}},
    )()
    monkeypatch.setattr(type(llm._chat_model), "invoke", lambda self, prompt: fake_message)

    miss = llm.invoke("prompt")
    hit = llm.invoke("prompt")

    assert (miss.cache_hit, miss.input_tokens, miss.output_tokens) == (False, 120, 30)
    assert (hit.cache_hit, hit.input_tokens, hit.output_tokens) == (True, 0, 0)
    assert miss.latency_seconds >= 0.0 and hit.latency_seconds >= 0.0


@pytest.fixture
def fresh_shared_rate_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_module, "_shared_rate_limiters", {})


@pytest.mark.usefixtures("fresh_shared_rate_limiter")
def test_shared_rate_limiter_defaults_to_the_in_memory_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "rate_limiter_backend", "memory")

    assert isinstance(get_shared_rate_limiter(), TokenBucket)


@pytest.mark.usefixtures("fresh_shared_rate_limiter")
def test_shared_rate_limiter_uses_redis_when_configured_and_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "rate_limiter_backend", "redis")
    monkeypatch.setattr(llm_module, "get_redis_client", lambda: fakeredis.FakeRedis())

    assert isinstance(get_shared_rate_limiter(), RedisTokenBucket)


@pytest.mark.usefixtures("fresh_shared_rate_limiter")
def test_shared_rate_limiter_falls_back_to_memory_when_redis_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "rate_limiter_backend", "redis")
    monkeypatch.setattr(llm_module, "get_redis_client", lambda: None)

    assert isinstance(get_shared_rate_limiter(), TokenBucket)
