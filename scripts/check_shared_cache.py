import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
import redis  # noqa: E402

from src.agent.llm_cache import REDIS_KEY_PREFIX  # noqa: E402
from src.config import settings  # noqa: E402

# Recusada pelo guardrail: carrega embeddings e reranker sem chamar a Groq, para a
# medicao seguinte nao incluir o arranque dos modelos.
WARM_UP_QUESTION = "Qual é a capital da Austrália?"
TIMEOUT_SECONDS = 600.0


def count_cache_keys(client: redis.Redis) -> int:
    return sum(1 for _ in client.scan_iter(f"{REDIS_KEY_PREFIX}*"))


def timed_query(base_url: str, question: str) -> dict:
    started = time.perf_counter()
    response = httpx.post(f"{base_url}/query", json={"question": question}, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    body = response.json()
    return {
        "instance": base_url,
        "seconds": round(time.perf_counter() - started, 3),
        "is_confident": body["is_confident"],
        "answer_preview": body["answer"][:120],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Duas instancias da API com cache Redis: a segunda deve servir da cache."
    )
    parser.add_argument("question")
    # 127.0.0.1 e nao localhost: no Windows, localhost tenta primeiro IPv6 e uma instancia
    # ligada so a 127.0.0.1 ganha ~2 s por pedido (medido), o que esconderia o efeito da cache.
    parser.add_argument("--instance-a", default="http://127.0.0.1:8000")
    parser.add_argument("--instance-b", default="http://127.0.0.1:8002")
    args = parser.parse_args()

    client = redis.Redis.from_url(settings.redis_url)
    for base_url in (args.instance_a, args.instance_b):
        timed_query(base_url, WARM_UP_QUESTION)

    keys_before = count_cache_keys(client)
    first = timed_query(args.instance_a, args.question)
    keys_after_first = count_cache_keys(client)
    second = timed_query(args.instance_b, args.question)
    keys_after_second = count_cache_keys(client)

    print(
        json.dumps(
            {
                "question": args.question,
                "redis_cache_keys": {
                    "before": keys_before,
                    "after_instance_a": keys_after_first,
                    "after_instance_b": keys_after_second,
                },
                "instance_a": first,
                "instance_b": second,
                "same_answer": first["answer_preview"] == second["answer_preview"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
