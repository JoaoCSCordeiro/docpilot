# Redis: shared LLM cache and distributed rate limiter (Block 20)

## What changed

- `redis:7-alpine` service in `docker-compose.yml` (host port 6379; the
  Langfuse Redis in `docker-compose.observability.yml` publishes no host
  port, so the two do not collide), `maxmemory 128mb` with `allkeys-lru`.
- LLM response cache (`src/agent/llm_cache.py`): `SQLiteResponseCache`
  (the previous behaviour) and `RedisResponseCache`, chosen by
  `LLM_CACHE_BACKEND=sqlite|redis`. Redis keys are `docpilot:llm:` plus the
  same SHA-256 of model and prompt used by SQLite, with a TTL
  (`LLM_CACHE_TTL_SECONDS`, default 7 days, 0 = no expiry).
- Groq rate limiter (`src/agent/rate_limiter.py`): `RedisTokenBucket`, a
  token bucket implemented as a Lua script, chosen by
  `RATE_LIMITER_BACKEND=memory|redis`. Redis runs the script atomically
  (read, refill, take, write), and the script uses the Redis clock (`TIME`),
  so replicas need neither a lock nor synchronised clocks. All processes
  share one key, `docpilot:ratelimit:groq`.
- Fallback: if Redis does not answer `PING` at start-up, the process uses
  SQLite and the in-memory bucket; if a Redis operation fails later, that
  operation falls back to them and logs a warning. Socket timeouts are 0.5 s.
- Defaults: outside Docker `.env.example` keeps `sqlite` and `memory`, so
  without Redis the behaviour is the same as before. The Compose file sets
  both to `redis`.
- No query-embedding cache: see "Decision" below.

The same block hardened the Compose setup: the API image runs as a
non-root user (`docpilot`, uid 1000) with a `HEALTHCHECK` on the new
`GET /health`; every service has a healthcheck and
`restart: unless-stopped`; the API waits for Qdrant, MongoDB and Redis to
be healthy; `POST /query` rejects questions longer than
`MAX_QUESTION_LENGTH` (2000 characters, the limit the MCP tools already
used) with 422. The MCP HTTP transport already bound to `127.0.0.1` by
default; it has no authentication and is meant for a trusted local machine.

## Evidence

All on 2026-10-18, on a laptop CPU (Windows 10, Docker Desktop), from the
working tree on top of commit `56b0e62`.

### Two API instances share the cache

Instance A: the API container from `docker compose up -d` (port 8000).
Instance B: `uvicorn src.api.main:app --port 8002` on the host, with
`LLM_CACHE_BACKEND=redis RATE_LIMITER_BACKEND=redis`. Both point at the same
Redis. Command: `python -X utf8 scripts/check_shared_cache.py "Quantos agentes tem o Financial Crew e por que ordem correm?"`
(both instances are first warmed up with a question the guardrail refuses,
so model loading is not measured).

| Step | Redis cache keys | Groq usage log lines (A / B) | Latency |
|---|---|---|---|
| Before | 1 | 1 / 252 | |
| Question to A | 2 | 2 / 252 | 1.531 s |
| Same question to B | 2 | 2 / 252 | 0.523 s |

A made the Groq call and stored the answer; B returned the same answer from
Redis without calling Groq. The remaining 0.5 s is retrieval and reranking
on CPU. (A first attempt measured B at ~2.6 s per request even on cache
hits; the cause was the client resolving `localhost` to IPv6 first on
Windows while B listened only on `127.0.0.1`. The script now uses
`127.0.0.1`.)

### Several processes share the rate limit

`python -X utf8 scripts/check_shared_rate_limit.py`: N processes, each with
its own Redis client, try to take tokens from one fresh bucket at the same
time; the refill period is one hour, so exactly `capacity` tokens may be
granted.

| Processes x attempts | Capacity | Granted per process | Granted total |
|---|---|---|---|
| 2 x 10 | 5 | 2, 3 | 5 |
| 4 x 25 | 20 | 2, 5, 6, 7 | 20 |

The same property is tested in CI with `fakeredis` (two clients of one
server, 20 threads, capacity 5: exactly 5 granted).

### Without Redis

With instance B running and the Redis container stopped, a question already
cached in Redis returned 200 in 4.878 s: the Redis read, the rate limiter and
the Redis write each timed out (0.5 s) and fell back to SQLite and the
in-memory bucket, with a warning in the log for each; the question was not
in SQLite, so Groq was called once. A question refused by the guardrail
(no LLM) returned in 0.523 s.

### LLM evaluation repeated: calls saved and latency

`GROQ_MAX_CALLS_PER_MINUTE=3 LLM_CACHE_BACKEND=redis RATE_LIMITER_BACKEND=redis python -X utf8 scripts/run_llm_evaluation.py --skip-judge --output-dir docs/evaluation/redis-cache/cold`,
then the same command with `--output-dir docs/evaluation/redis-cache/warm`.
Redis started with no entries for these prompts. 58 cases, 47 reach the
generator.

| Run | Groq generation calls | Cache hits | Latency p50 | Latency p95 | Tokens per generation (mean, in / out) |
|---|---|---|---|---|---|
| Cold | 47 | 0 | 756.2 ms | 1538.3 ms | 1079.5 / 244.0 |
| Warm | 0 | 47 | 0.93 ms | 1.13 ms | 0 / 0 |

Latency on a miss is the Groq call alone (rate limiter wait excluded); on a
hit it is the Redis lookup. The warm run reproduced all 58 answers of the
cold run.

Read-latency microbenchmark (`python -X utf8 scripts/measure_cache_latency.py`,
1500-byte value, N = 500 reads each):

| Operation | p50 | p95 |
|---|---|---|
| SQLite get, hit | 1.241 ms | 1.900 ms |
| SQLite get, miss | 1.428 ms | 2.147 ms |
| Redis get, hit | 0.981 ms | 1.270 ms |
| Redis get, miss | 0.971 ms | 1.238 ms |
| Query embedding (`multilingual-e5-small`, N = 50) | 40.079 ms | 52.187 ms |

## Findings

- The generator is not deterministic at temperature 0: the cold run is a
  second sample of the same 47 prompts, and only 16 of the 47 answers are
  identical to the prompt v3 run in `docs/evaluation/prompt-v3/`. One
  decision changed (case 16 became an abstention); the injection leaks were
  the same (2 of 10). This is also why the cache matters for evaluation: a
  repeated run reproduces one sample, it does not draw a new one.
- On a single machine, Redis and SQLite reads cost about the same (around
  1 ms); the gain from Redis is sharing, not speed.

## Decision: no query-embedding cache

The plan allowed it only if measurement showed a gain. A cached embedding
would save at most about 39 ms (40 ms to embed, 1 ms to read from Redis), and
only for a question repeated exactly, which still pays about 215 ms of
reranking. Not implemented.

## Limitations

- While Redis is down, each replica falls back to its own in-memory limit,
  so the sum across replicas can exceed the real Groq limit, and each
  request pays up to about 1.5 s of timeouts. There is no circuit breaker.
  A process that starts while Redis is down keeps the local backends until
  it restarts.
- Every process sharing the bucket must use the same
  `GROQ_MAX_CALLS_PER_MINUTE`, because the capacity is passed on each call.
- The two-instance test ran one API in Docker and one on the host, not two
  replicas in Kubernetes; the optional k3s step with two replicas was not
  done.
- `allkeys-lru` may evict the rate limiter key under memory pressure, which
  resets the bucket to full; with 128 MB and the current corpus this was not
  observed.
