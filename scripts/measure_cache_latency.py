import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import redis  # noqa: E402

from src.agent.llm_cache import RedisResponseCache, SQLiteResponseCache  # noqa: E402
from src.config import settings  # noqa: E402
from src.retrieval.embeddings import embed_queries  # noqa: E402

MODEL = "latency-check"
PROMPT = "prompt de medicao"
# Tamanho tipico de uma resposta do gerador no eval (~1-2 KB).
RESPONSE = "x" * 1500
QUERY = "Como configuro o MongoDB no docker compose?"


def time_ms(operation: Callable[[], object], repetitions: int) -> dict:
    samples = []
    for _ in range(repetitions):
        started = time.perf_counter()
        operation()
        samples.append((time.perf_counter() - started) * 1000)
    samples.sort()
    return {
        "n": repetitions,
        "p50_ms": round(statistics.median(samples), 3),
        "p95_ms": round(samples[int(0.95 * (len(samples) - 1))], 3),
        "mean_ms": round(statistics.fmean(samples), 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Latencia de leitura da cache (SQLite vs Redis) e do embedding da query."
    )
    parser.add_argument("--repetitions", type=int, default=500)
    parser.add_argument("--embedding-repetitions", type=int, default=50)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        sqlite_cache = SQLiteResponseCache(Path(tmp) / "latency.db")
        sqlite_cache.set(MODEL, PROMPT, RESPONSE)
        sqlite_hit = time_ms(lambda: sqlite_cache.get(MODEL, PROMPT), args.repetitions)
        sqlite_miss = time_ms(lambda: sqlite_cache.get(MODEL, "outro"), args.repetitions)

    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    redis_cache = RedisResponseCache(client, ttl_seconds=300)
    redis_cache.set(MODEL, PROMPT, RESPONSE)
    redis_hit = time_ms(lambda: redis_cache.get(MODEL, PROMPT), args.repetitions)
    redis_miss = time_ms(lambda: redis_cache.get(MODEL, "outro"), args.repetitions)

    embed_queries([QUERY])  # carrega o modelo fora da medicao
    embedding = time_ms(lambda: embed_queries([QUERY]), args.embedding_repetitions)

    print(
        json.dumps(
            {
                "redis_url": settings.redis_url,
                "response_bytes": len(RESPONSE),
                "sqlite_get_hit": sqlite_hit,
                "sqlite_get_miss": sqlite_miss,
                "redis_get_hit": redis_hit,
                "redis_get_miss": redis_miss,
                "embedding_model": settings.embedding_model_name,
                "query_embedding": embedding,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
