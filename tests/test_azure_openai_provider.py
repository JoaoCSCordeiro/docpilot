import json

import fakeredis
import httpx
import pytest
from langchain_groq import ChatGroq
from langchain_openai import AzureChatOpenAI

from src.agent import llm as llm_module
from src.agent.llm import AZURE_OPENAI, GROQ, GuardedLLM, get_llm, get_shared_rate_limiter
from src.agent.llm_cache import cache_key
from src.agent.rate_limiter import RedisTokenBucket, TokenBucket
from src.config import settings
from src.evaluation.judge import get_judge_llm

ENDPOINT = "https://docpilot-test.openai.azure.com"


@pytest.fixture(autouse=True)
def azure_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "groq_api_key", "gsk-test-not-a-real-key")
    monkeypatch.setattr(settings, "azure_openai_endpoint", ENDPOINT)
    monkeypatch.setattr(settings, "azure_openai_api_key", "azure-test-not-a-real-key")
    monkeypatch.setattr(settings, "azure_openai_deployment", "gpt-4.1-mini")
    monkeypatch.setattr(settings, "azure_openai_api_version", "2024-10-21")
    monkeypatch.setattr(settings, "rate_limiter_backend", "memory")
    monkeypatch.setattr(llm_module, "_shared_rate_limiters", {})


@pytest.fixture
def in_memory_cache(monkeypatch: pytest.MonkeyPatch) -> dict:
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
    return store


def _fake_message(content: str = "ok"):
    return type(
        "FakeMessage",
        (),
        {"content": content, "usage_metadata": {"input_tokens": 50, "output_tokens": 10}},
    )()


def test_azure_provider_builds_an_azure_chat_model_for_the_configured_deployment() -> None:
    llm = get_llm(provider=AZURE_OPENAI)

    assert isinstance(llm._chat_model, AzureChatOpenAI)
    assert llm.provider == AZURE_OPENAI
    assert llm.model_name == "gpt-4.1-mini"
    assert llm._chat_model.deployment_name == "gpt-4.1-mini"
    assert llm._chat_model.azure_endpoint == ENDPOINT
    assert llm._chat_model.openai_api_version == "2024-10-21"
    assert llm._chat_model.temperature == 0.0
    assert llm._chat_model.max_tokens == settings.azure_openai_max_tokens


def test_llm_provider_setting_selects_the_default_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert isinstance(get_llm()._chat_model, ChatGroq)

    monkeypatch.setattr(settings, "llm_provider", AZURE_OPENAI)

    assert isinstance(get_llm()._chat_model, AzureChatOpenAI)


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        get_llm(provider="bedrock")


def test_judge_stays_on_groq_when_the_generator_uses_azure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_provider", AZURE_OPENAI)

    judge = get_judge_llm()

    assert judge.provider == GROQ
    assert judge.model_name == settings.judge_model


def test_groq_cache_key_is_unchanged_and_azure_key_is_prefixed(
    monkeypatch: pytest.MonkeyPatch, in_memory_cache: dict
) -> None:
    groq_llm = get_llm(provider=GROQ)
    azure_llm = get_llm(provider=AZURE_OPENAI, model=settings.groq_model)
    for chat_class in (ChatGroq, AzureChatOpenAI):
        monkeypatch.setattr(chat_class, "invoke", lambda self, prompt: _fake_message())

    groq_llm.invoke("prompt")
    azure_llm.invoke("prompt")

    # Mesmo nome de modelo nos dois providers: sem o prefixo, o Azure leria a resposta
    # da Groq da cache.
    assert set(in_memory_cache) == {
        (settings.groq_model, "prompt"),
        (f"azure_openai:{settings.groq_model}", "prompt"),
    }
    assert groq_llm.call_count == azure_llm.call_count == 1


def test_groq_cache_entries_written_before_block_21_are_still_found() -> None:
    llm = get_llm(provider=GROQ)

    assert cache_key(llm.cache_model_key, "p") == cache_key(settings.groq_model, "p")


def test_azure_calls_are_cached_and_counted_like_groq_calls(
    monkeypatch: pytest.MonkeyPatch, in_memory_cache: dict
) -> None:
    llm = get_llm(provider=AZURE_OPENAI)
    monkeypatch.setattr(type(llm._chat_model), "invoke", lambda self, prompt: _fake_message())

    miss = llm.invoke("prompt")
    hit = llm.invoke("prompt")

    assert (miss.cache_hit, miss.input_tokens, miss.output_tokens) == (False, 50, 10)
    assert hit.cache_hit
    assert llm.call_count == 1


def test_no_cost_is_estimated_for_azure(
    monkeypatch: pytest.MonkeyPatch, in_memory_cache: dict
) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("o preco da Groq nao se aplica ao Azure")

    monkeypatch.setattr(llm_module, "estimate_groq_cost", fail)
    llm = get_llm(provider=AZURE_OPENAI, model=settings.groq_model)
    monkeypatch.setattr(type(llm._chat_model), "invoke", lambda self, prompt: _fake_message())

    assert llm.invoke("prompt").content == "ok"


def test_each_provider_has_its_own_rate_limiter() -> None:
    groq_limiter = get_shared_rate_limiter(GROQ)
    azure_limiter = get_shared_rate_limiter(AZURE_OPENAI)

    assert groq_limiter is not azure_limiter
    assert get_llm(provider=GROQ)._rate_limiter is groq_limiter
    assert get_llm(provider=AZURE_OPENAI)._rate_limiter is azure_limiter
    assert isinstance(azure_limiter, TokenBucket)
    assert azure_limiter.capacity == settings.azure_openai_max_calls_per_minute


def test_redis_rate_limit_key_for_groq_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rate_limiter_backend", "redis")
    monkeypatch.setattr(llm_module, "get_redis_client", lambda: fakeredis.FakeRedis())

    groq_limiter = get_shared_rate_limiter(GROQ)
    azure_limiter = get_shared_rate_limiter(AZURE_OPENAI)

    assert isinstance(groq_limiter, RedisTokenBucket)
    assert groq_limiter._key == "docpilot:ratelimit:groq"
    assert azure_limiter._key == "docpilot:ratelimit:azure_openai"


def test_azure_request_goes_to_the_deployment_url_with_the_api_key(
    monkeypatch: pytest.MonkeyPatch, in_memory_cache: dict
) -> None:
    # Pedido HTTP real do SDK da OpenAI, intercetado antes de sair da maquina.
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-4.1-mini",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "resposta"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
            },
        )

    chat_model = AzureChatOpenAI(
        azure_deployment="gpt-4.1-mini",
        azure_endpoint=ENDPOINT,
        api_key="azure-test-not-a-real-key",
        api_version="2024-10-21",
        temperature=0.0,
        max_tokens=64,
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    llm = GuardedLLM(chat_model, TokenBucket(capacity=10), "gpt-4.1-mini", provider=AZURE_OPENAI)

    response = llm.invoke("pergunta")

    assert response.content == "resposta"
    assert (response.input_tokens, response.output_tokens) == (12, 3)
    [request] = requests
    assert request.url.path == "/openai/deployments/gpt-4.1-mini/chat/completions"
    assert request.url.params["api-version"] == "2024-10-21"
    assert request.headers["api-key"] == "azure-test-not-a-real-key"
    body = json.loads(request.content)
    assert body["temperature"] == 0.0
    # O langchain-openai 0.3 envia max_tokens com o nome novo da API.
    assert body["max_completion_tokens"] == 64
    assert body["messages"] == [{"role": "user", "content": "pergunta"}]
