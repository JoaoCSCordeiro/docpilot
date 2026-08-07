from dataclasses import dataclass

from langchain_groq import ChatGroq

from src.agent.llm_cache import get_cached_response, store_response
from src.agent.rate_limiter import TokenBucket
from src.agent.usage_logger import log_usage
from src.config import settings


@dataclass
class LLMResponse:
    content: str


class GuardedGroqLLM:
    def __init__(self, chat_groq: ChatGroq, rate_limiter: TokenBucket) -> None:
        self._chat_groq = chat_groq
        self._rate_limiter = rate_limiter

    def invoke(self, prompt: str) -> LLMResponse:
        cached_content = get_cached_response(prompt)
        if cached_content is not None:
            return LLMResponse(content=cached_content)

        self._rate_limiter.acquire()
        response = self._chat_groq.invoke(prompt)

        usage = getattr(response, "usage_metadata", None) or {}
        log_usage(
            prompt_preview=prompt[:80],
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )

        store_response(prompt, response.content)
        return LLMResponse(content=response.content)


def get_llm() -> GuardedGroqLLM:
    chat_groq = ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=0.0,
        max_tokens=settings.groq_max_tokens,
    )
    rate_limiter = TokenBucket(
        capacity=settings.groq_max_calls_per_minute, refill_period_seconds=60.0
    )
    return GuardedGroqLLM(chat_groq, rate_limiter)
