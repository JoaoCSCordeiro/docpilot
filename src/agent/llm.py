import threading
import time
from dataclasses import dataclass
from typing import Any

from langchain_groq import ChatGroq

from src.agent.llm_cache import get_cached_response, store_response
from src.agent.rate_limiter import RateLimiter, RedisTokenBucket, TokenBucket
from src.agent.redis_client import get_redis_client
from src.agent.usage_logger import log_usage
from src.config import settings
from src.observability.tracing import observation

_TOKENS_PER_PRICE_UNIT = 1_000_000


@dataclass
class LLMResponse:
    content: str
    cache_hit: bool = False
    # Leitura da cache num hit; so a chamada a Groq num miss (sem a espera do rate limiter).
    latency_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


def estimate_groq_cost(input_tokens: int, output_tokens: int) -> dict[str, float]:
    input_cost = input_tokens * settings.groq_price_input_per_million / _TOKENS_PER_PRICE_UNIT
    output_cost = output_tokens * settings.groq_price_output_per_million / _TOKENS_PER_PRICE_UNIT
    return {"input": input_cost, "output": output_cost, "total": input_cost + output_cost}


class GuardedGroqLLM:
    def __init__(self, chat_groq: ChatGroq, rate_limiter: RateLimiter) -> None:
        self._chat_groq = chat_groq
        self._rate_limiter = rate_limiter
        self.groq_call_count = 0

    @property
    def model_name(self) -> str:
        return self._chat_groq.model_name

    def invoke(self, prompt: str) -> LLMResponse:
        model = self._chat_groq.model_name
        lookup_started = time.perf_counter()
        cached_content = get_cached_response(model, prompt)
        lookup_seconds = time.perf_counter() - lookup_started
        if cached_content is not None:
            with observation(
                "llm",
                as_type="generation",
                model=model,
                input=prompt,
                output=cached_content,
                metadata={"cache_hit": True},
                usage_details={"input": 0, "output": 0},
                cost_details={"total": 0.0},
            ):
                return LLMResponse(
                    content=cached_content, cache_hit=True, latency_seconds=lookup_seconds
                )

        # A espera do rate limiter fica fora da generation para a latencia medida ser a
        # da Groq; o tempo de espera vai em metadata.
        wait_started = time.monotonic()
        self._rate_limiter.acquire()
        rate_limit_wait_seconds = time.monotonic() - wait_started

        with observation(
            "llm",
            as_type="generation",
            model=model,
            input=prompt,
            model_parameters={
                "temperature": self._chat_groq.temperature,
                "max_tokens": self._chat_groq.max_tokens,
            },
            metadata={
                "cache_hit": False,
                "rate_limit_wait_seconds": round(rate_limit_wait_seconds, 3),
            },
        ) as generation:
            # Conta tentativas, nao sucessos: um pedido rejeitado tambem gasta quota.
            self.groq_call_count += 1
            call_started = time.perf_counter()
            response = self._chat_groq.invoke(prompt)
            call_seconds = time.perf_counter() - call_started
            usage = getattr(response, "usage_metadata", None) or {}
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cost = {}
            # O preco configurado e o do gerador; para outro modelo (ex.: o juiz) nao se
            # inventa um custo.
            if model == settings.groq_model:
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

        store_response(model, prompt, response.content)
        return LLMResponse(
            content=response.content,
            latency_seconds=call_seconds,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


RATE_LIMIT_REDIS_KEY = "docpilot:ratelimit:groq"

_shared_rate_limiter: RateLimiter | None = None
_shared_rate_limiter_lock = threading.Lock()


def _build_rate_limiter() -> RateLimiter:
    local_bucket = TokenBucket(
        capacity=settings.groq_max_calls_per_minute, refill_period_seconds=60.0
    )
    if settings.rate_limiter_backend != "redis":
        return local_bucket
    client = get_redis_client()
    if client is None:
        return local_bucket
    # Uma chave por quota Groq: todas as replicas e processos descontam do mesmo bucket.
    return RedisTokenBucket(
        client,
        RATE_LIMIT_REDIS_KEY,
        capacity=settings.groq_max_calls_per_minute,
        refill_period_seconds=60.0,
        fallback=local_bucket,
    )


def get_shared_rate_limiter() -> RateLimiter:
    # Um limiter por processo, partilhado por todos os LLMs (gerador e juiz). E mais
    # conservador do que o necessario se a Groq limitar cada modelo em separado, mas
    # nunca soma limites de instancias diferentes. Com o backend Redis, o mesmo vale
    # entre processos e replicas.
    global _shared_rate_limiter
    with _shared_rate_limiter_lock:
        if _shared_rate_limiter is None:
            _shared_rate_limiter = _build_rate_limiter()
        return _shared_rate_limiter


def get_llm(
    model: str | None = None,
    max_tokens: int | None = None,
    model_kwargs: dict[str, Any] | None = None,
) -> GuardedGroqLLM:
    chat_groq = ChatGroq(
        model=model or settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=0.0,
        max_tokens=max_tokens or settings.groq_max_tokens,
        model_kwargs=model_kwargs or {},
    )
    return GuardedGroqLLM(chat_groq, get_shared_rate_limiter())
