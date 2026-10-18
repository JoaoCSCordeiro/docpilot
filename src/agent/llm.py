import threading
import time
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_groq import ChatGroq
from langchain_openai import AzureChatOpenAI

from src.agent.llm_cache import get_cached_response, store_response
from src.agent.rate_limiter import RateLimiter, RedisTokenBucket, TokenBucket
from src.agent.redis_client import get_redis_client
from src.agent.usage_logger import log_usage
from src.config import settings
from src.observability.tracing import observation

_TOKENS_PER_PRICE_UNIT = 1_000_000

GROQ = "groq"
AZURE_OPENAI = "azure_openai"
PROVIDERS = (GROQ, AZURE_OPENAI)


@dataclass
class LLMResponse:
    content: str
    cache_hit: bool = False
    # Leitura da cache num hit; so a chamada ao provider num miss (sem a espera do rate
    # limiter).
    latency_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


def estimate_groq_cost(input_tokens: int, output_tokens: int) -> dict[str, float]:
    input_cost = input_tokens * settings.groq_price_input_per_million / _TOKENS_PER_PRICE_UNIT
    output_cost = output_tokens * settings.groq_price_output_per_million / _TOKENS_PER_PRICE_UNIT
    return {"input": input_cost, "output": output_cost, "total": input_cost + output_cost}


class GuardedLLM:
    # Cache, rate limiter, tracing e contagem de chamadas a volta de qualquer chat model
    # do LangChain. O ChatGroq e o AzureChatOpenAI expoem temperature e max_tokens.
    def __init__(
        self,
        chat_model: BaseChatModel,
        rate_limiter: RateLimiter,
        model_name: str,
        provider: str = GROQ,
    ) -> None:
        self._chat_model = chat_model
        self._rate_limiter = rate_limiter
        self.provider = provider
        self.model_name = model_name
        self.call_count = 0

    @property
    def cache_model_key(self) -> str:
        # A Groq mantem a chave antiga (so o modelo): muda-la invalidava a cache de que
        # os relatorios dev e held-out se reproduzem. Nos outros providers o prefixo
        # evita colisoes entre um deployment Azure e um modelo Groq com o mesmo nome.
        if self.provider == GROQ:
            return self.model_name
        return f"{self.provider}:{self.model_name}"

    def invoke(self, prompt: str) -> LLMResponse:
        model = self.model_name
        lookup_started = time.perf_counter()
        cached_content = get_cached_response(self.cache_model_key, prompt)
        lookup_seconds = time.perf_counter() - lookup_started
        if cached_content is not None:
            with observation(
                "llm",
                as_type="generation",
                model=model,
                input=prompt,
                output=cached_content,
                metadata={"cache_hit": True, "provider": self.provider},
                usage_details={"input": 0, "output": 0},
                cost_details={"total": 0.0},
            ):
                return LLMResponse(
                    content=cached_content, cache_hit=True, latency_seconds=lookup_seconds
                )

        # A espera do rate limiter fica fora da generation para a latencia medida ser a
        # do provider; o tempo de espera vai em metadata.
        wait_started = time.monotonic()
        self._rate_limiter.acquire()
        rate_limit_wait_seconds = time.monotonic() - wait_started

        with observation(
            "llm",
            as_type="generation",
            model=model,
            input=prompt,
            model_parameters={
                "temperature": self._chat_model.temperature,
                "max_tokens": self._chat_model.max_tokens,
            },
            metadata={
                "cache_hit": False,
                "provider": self.provider,
                "rate_limit_wait_seconds": round(rate_limit_wait_seconds, 3),
            },
        ) as generation:
            # Conta tentativas, nao sucessos: um pedido rejeitado tambem gasta quota.
            self.call_count += 1
            call_started = time.perf_counter()
            response = self._chat_model.invoke(prompt)
            call_seconds = time.perf_counter() - call_started
            usage = getattr(response, "usage_metadata", None) or {}
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cost = {}
            # O preco configurado e o do gerador Groq; para outro modelo (ex.: o juiz) ou
            # outro provider nao se inventa um custo.
            if self.provider == GROQ and model == settings.groq_model:
                cost["cost_details"] = estimate_groq_cost(input_tokens, output_tokens)
            generation.update(
                output=response.content,
                usage_details={"input": input_tokens, "output": output_tokens},
                **cost,
            )

        log_usage(
            prompt_preview=prompt[:80],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=usage.get("total_tokens", 0),
        )

        store_response(self.cache_model_key, prompt, response.content)
        return LLMResponse(
            content=response.content,
            latency_seconds=call_seconds,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


# A chave da Groq e a de antes do Bloco 21; cada provider tem a sua quota e o seu bucket.
RATE_LIMIT_REDIS_KEYS = {
    GROQ: "docpilot:ratelimit:groq",
    AZURE_OPENAI: "docpilot:ratelimit:azure_openai",
}

_shared_rate_limiters: dict[str, RateLimiter] = {}
_shared_rate_limiter_lock = threading.Lock()


def _calls_per_minute(provider: str) -> int:
    if provider == AZURE_OPENAI:
        return settings.azure_openai_max_calls_per_minute
    return settings.groq_max_calls_per_minute


def _build_rate_limiter(provider: str) -> RateLimiter:
    capacity = _calls_per_minute(provider)
    local_bucket = TokenBucket(capacity=capacity, refill_period_seconds=60.0)
    if settings.rate_limiter_backend != "redis":
        return local_bucket
    client = get_redis_client()
    if client is None:
        return local_bucket
    # Uma chave por quota de provider: todas as replicas e processos descontam do mesmo
    # bucket.
    return RedisTokenBucket(
        client,
        RATE_LIMIT_REDIS_KEYS[provider],
        capacity=capacity,
        refill_period_seconds=60.0,
        fallback=local_bucket,
    )


def get_shared_rate_limiter(provider: str = GROQ) -> RateLimiter:
    # Um limiter por provider e por processo, partilhado por todos os LLMs desse provider
    # (gerador e juiz). E mais conservador do que o necessario se a Groq limitar cada
    # modelo em separado, mas nunca soma limites de instancias diferentes. Com o backend
    # Redis, o mesmo vale entre processos e replicas.
    with _shared_rate_limiter_lock:
        if provider not in _shared_rate_limiters:
            _shared_rate_limiters[provider] = _build_rate_limiter(provider)
        return _shared_rate_limiters[provider]


def get_llm(
    model: str | None = None,
    max_tokens: int | None = None,
    model_kwargs: dict[str, Any] | None = None,
    provider: str | None = None,
) -> GuardedLLM:
    provider = provider or settings.llm_provider
    if provider == AZURE_OPENAI:
        # No Azure o "modelo" e o nome do deployment, nao o do modelo base.
        deployment = model or settings.azure_openai_deployment
        chat_model: BaseChatModel = AzureChatOpenAI(
            azure_deployment=deployment,
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            temperature=0.0,
            max_tokens=max_tokens or settings.azure_openai_max_tokens,
            model_kwargs=model_kwargs or {},
        )
        return GuardedLLM(chat_model, get_shared_rate_limiter(provider), deployment, provider)
    if provider != GROQ:
        raise ValueError(f"LLM_PROVIDER desconhecido: {provider!r} (validos: {PROVIDERS})")
    model = model or settings.groq_model
    chat_model = ChatGroq(
        model=model,
        api_key=settings.groq_api_key,
        temperature=0.0,
        max_tokens=max_tokens or settings.groq_max_tokens,
        model_kwargs=model_kwargs or {},
    )
    return GuardedLLM(chat_model, get_shared_rate_limiter(provider), model, provider)
