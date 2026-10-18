import argparse
import json
import multiprocessing
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import redis  # noqa: E402

from src.agent.rate_limiter import RedisTokenBucket  # noqa: E402
from src.config import settings  # noqa: E402

# Periodo longo: durante a verificacao (segundos) nao chega a reabastecer nenhum token,
# por isso o total concedido tem de ser exatamente a capacidade.
REFILL_PERIOD_SECONDS = 3600.0


def worker(key: str, capacity: int, attempts: int, start, results) -> None:
    client = redis.Redis.from_url(settings.redis_url)
    bucket = RedisTokenBucket(
        client, key, capacity=capacity, refill_period_seconds=REFILL_PERIOD_SECONDS
    )
    start.wait()
    results.put(sum(bucket.try_acquire() == 0.0 for _ in range(attempts)))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Varios processos contra o mesmo bucket no Redis real; conta os tokens."
    )
    parser.add_argument("--processes", type=int, default=2)
    parser.add_argument("--attempts", type=int, default=10, help="Tentativas por processo.")
    parser.add_argument("--capacity", type=int, default=5)
    args = parser.parse_args()

    key = f"docpilot:ratelimit:check-{uuid.uuid4().hex[:8]}"
    start = multiprocessing.Barrier(args.processes)
    results = multiprocessing.Queue()
    processes = [
        multiprocessing.Process(
            target=worker, args=(key, args.capacity, args.attempts, start, results)
        )
        for _ in range(args.processes)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join()

    granted_per_process = sorted(results.get() for _ in processes)
    redis.Redis.from_url(settings.redis_url).delete(key)
    print(
        json.dumps(
            {
                "redis_url": settings.redis_url,
                "processes": args.processes,
                "attempts_per_process": args.attempts,
                "capacity": args.capacity,
                "granted_per_process": granted_per_process,
                "granted_total": sum(granted_per_process),
                "ok": sum(granted_per_process) == args.capacity,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
