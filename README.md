# DocPilot

![CI](https://github.com/JoaoCSCordeiro/docpilot/actions/workflows/ci.yml/badge.svg)

## Overview

DocPilot is a question answering agent for technical documentation, built with
Retrieval-Augmented Generation (RAG). The system retrieves relevant chunks
from a vector database, reranks them with a cross-encoder, and generates an
answer with an LLM, but only when a deterministic confidence guardrail judges
the retrieved context sufficient. When it is not, the agent refuses to
answer instead of guessing.

The corpus used for indexing and evaluation is the documentation of other
projects in the same portfolio (README files), which keeps the demo
self-contained and avoids depending on external or licensed data.

The project targets three technical areas: cloud infrastructure as code
(Terraform, AWS, Kubernetes), retrieval-augmented generation with a real
vector database (not a thin wrapper over an API), and agent orchestration
with LangGraph.

## Architecture

```
Documents (raw) -> Ingestion + Chunking -> Embeddings -> Qdrant (vector store)
                                                              |
                                                              v
User question -> Retrieval -> Reranking -> Confidence guardrail
                                                              |
                                                              v
                                          LangGraph agent -> Answer / Refusal
                                                              |
                                              +---------------+---------------+
                                              v                               v
                                FastAPI (POST /query)            MCP server (stdio / HTTP)
                                              |                               |
                                              +---------------+---------------+
                                                              v
                                      MongoDB trace log  +  Langfuse traces (optional)
```

Components:

- Ingestion (`src/ingestion`): loads markdown/text files and splits them into
  chunks. Two strategies are implemented and compared, fixed-size and
  semantic (paragraph/sentence aware).
- Retrieval (`src/retrieval`): indexes each chunk in Qdrant with two named
  vectors, a dense multilingual embedding (`sentence-transformers`, local,
  CPU, no external API) and a sparse BM25 vector (`fastembed`, IDF computed
  by Qdrant). Retrieval runs in `dense`, `sparse` or `hybrid` mode
  (`RETRIEVAL_MODE`); hybrid fuses both rankings with Reciprocal Rank Fusion
  through the Qdrant Query API. A multilingual cross-encoder reranks the
  candidates before they reach the agent. The defaults were chosen by an
  ablation, see `docs/hybrid-retrieval.md`.
- Agent (`src/agent`): a LangGraph state graph orchestrates
  retrieve, rerank, assess confidence, and generate answer or refuse. The
  confidence guardrail is a separate, testable function, not left to the
  LLM's judgment. Groq (`langchain-groq`) is used for generation, guarded by
  a token bucket rate limiter, a local SQLite response cache, and a
  conservative `max_tokens` limit.
- API (`src/api`): a FastAPI application exposes the agent over HTTP
  (`POST /query`), with request/response validation via Pydantic.
  Every query is persisted as a trace document in MongoDB (`src/agent/query_log.py`),
  recording the retrieved chunks, reranked chunks, confidence, and answer.
- MCP server (`src/mcp_server`): exposes the same retrieval and agent
  functions as Model Context Protocol tools, so MCP clients can use DocPilot
  directly. Tested with Claude Code and with the SDK's own client.
- Observability (`src/observability`): optional Langfuse tracing, one trace
  per request with a span per graph node and the LLM call recorded as a
  generation. A no-op when Langfuse keys are not configured.
- Evaluation (`src/evaluation`): retrieval metrics (recall@k, precision@k,
  MRR, split by question and document language), deterministic answer checks
  (refusal, source citations, prompt injection canary), and an
  LLM-as-a-judge for faithfulness and answer relevance, over a 58-case
  annotated dataset. A retrieval-only version runs as a gate in CI.

## Setup

### Docker Compose (recommended)

Requires Docker and Docker Compose. Full instructions in
`docs/local-setup.md`; summary:

```
cp .env.example .env
# edit .env and set GROQ_API_KEY
docker compose up -d --build
docker compose exec api python scripts/index_documents.py
```

The API is then available at `http://localhost:8000/docs`.

### Local (without Docker)

Requires Python 3.11+ and a Qdrant/MongoDB instance reachable at the hosts
configured in `.env` (defaults assume `localhost`, started via
`docker compose up -d qdrant mongo`).

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
python scripts/index_documents.py
uvicorn src.api.main:app --reload
```

## Usage

Ask a question through the API:

```
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"What library does the ASL translator use for hand detection?\"}"
```

Or from the command line, without running the API:

```
python scripts/ask_agent.py "What library does the ASL translator use for hand detection?"
```

Other scripts:

- `scripts/index_documents.py`: runs the full ingestion pipeline (load, chunk,
  dense and sparse embeddings, index) against `data/raw`. `--recreate`
  rebuilds the collection; `--collection`, `--embedding-model` and
  `--bm25-language` override the configured defaults.
- `scripts/run_retrieval_ablation.py`: compares embedding models, retrieval
  modes, BM25 stemming options and rerankers on the 58-case dataset without
  calling an LLM, and writes `docs/evaluation/retrieval-ablation.json`.
- `scripts/run_evaluation.py`: runs the original 25-question dataset
  (`data/evaluation/qa_dataset.json`) against the retrieval pipeline and
  prints recall/precision metrics.
- `scripts/run_llm_evaluation.py`: runs the 58-case dataset
  (`data/evaluation/qa_dataset_v2.json`) through the full agent, applies the
  deterministic checks and the LLM judge, and writes a report to
  `docs/evaluation/`. `--dry-run` prints the number of Groq calls it would
  make without calling the LLM.
- `scripts/check_retrieval_gate.py`: retrieval-only evaluation compared with
  `data/evaluation/baseline.json`; exits with code 1 on a regression.
- `scripts/judge_calibration.py`: writes a blind labelling sheet for the
  judge and reports agreement once the labels are filled in.

Every answer, confident or refused, is logged as a document in MongoDB
(collection `query_traces`), inspectable with `mongosh` or Compass; see
`docs/mongodb-query-log.md` for the schema and the reasoning behind using
MongoDB for this specific case.

### MCP Server

`scripts/run_mcp_server.py` runs DocPilot as an MCP server (official
Python SDK, `mcp` 2.x, `MCPServer`). Three tools are exposed:

- `search_docs(query, top_k)`: vector search plus cross-encoder reranking,
  returning `source`, `position`, score, and text for each chunk. It does
  not call the LLM. `top_k` is limited to 1-20.
- `ask_docpilot(question)`: runs the full agent and returns the answer,
  the decision (`answered` or `refused`), the confidence, and the sources.
- `list_sources()`: lists the indexed documents with their chunk counts.

The default transport is stdio. Register it in Claude Code (local scope,
stored in `~/.claude.json`, not in the repository):

```
claude mcp add docpilot --scope local -- "<repo>\.venv\Scripts\python.exe" "<repo>\scripts\run_mcp_server.py"
claude mcp list
```

Equivalent entry for clients configured through JSON, such as Claude
Desktop's `claude_desktop_config.json` (this format follows the MCP
convention but was not tested with Claude Desktop):

```
{
  "mcpServers": {
    "docpilot": {
      "command": "<repo>\\.venv\\Scripts\\python.exe",
      "args": ["<repo>\\scripts\\run_mcp_server.py"]
    }
  }
}
```

Streamable HTTP is available as a second transport, bound to
`127.0.0.1:8001` by default (`MCP_HTTP_HOST`/`MCP_HTTP_PORT`), with no
authentication:

```
python scripts/run_mcp_server.py --transport streamable-http
```

Qdrant must be running for every tool, and `GROQ_API_KEY` is needed only
by `ask_docpilot`. Tool output is document text, so a document containing
instructions can attempt prompt injection against the client agent; see
`docs/mcp-evidence.md` for the real calls made from Claude Code and for
the mitigations that exist and those that do not.

### Observability

Tracing uses a self-hosted Langfuse instance (`docker-compose.observability.yml`,
Langfuse 4.59.0, six containers, about 2.75 GiB of RAM measured with
`docker stats`) and the Langfuse Python SDK v5, which is built on
OpenTelemetry. It is enabled only when `LANGFUSE_PUBLIC_KEY` and
`LANGFUSE_SECRET_KEY` are set; otherwise every tracing call is a no-op.

```
cp .env.observability.example .env.observability   # replace every value
docker compose -f docker-compose.observability.yml --env-file .env.observability up -d
```

Each request from the API, the MCP server, or `scripts/ask_agent.py` produces
one trace, tagged with its entry point:

```
docpilot-query (agent)              question -> answer, decision, confidence
|-- retrieve (retriever)            top-k chunks with source, position, score
|-- rerank                          reranked chunks
|-- assess_confidence (guardrail)   confidence, threshold, decision
`-- generate_answer | refuse
    `-- llm (generation)            model, tokens, estimated cost, cache hit/miss
```

Cost is an estimate based on Groq's public price for `openai/gpt-oss-120b`
($0.15 per million input tokens, $0.60 per million output tokens,
consulted on 2026-10-16); the free tier itself costs nothing. Traces are
exported in the background, and a request still completes when Langfuse is
down. MongoDB keeps the application's own query history; Langfuse is the
optional debugging layer. `docs/observability/` contains 15 real traces
exported from the local instance and the analysis of what they showed,
including an incorrect answer that passed the confidence guardrail.

## Evaluation Results

Full methodology and per-case results in `docs/hybrid-retrieval.md`
(retrieval ablation, Block 19), `docs/evaluation/README.md` (answer
evaluation, Block 18) and `docs/evaluation-results.md` (original retrieval
evaluation). The dataset has 58 cases: 40 in-scope questions (25 Portuguese,
15 English), 8 out-of-scope questions, and 10 prompt injection cases.

Retrieval, 40 in-scope questions, top 5. Before: `all-MiniLM-L6-v2` dense
with the English `ms-marco-MiniLM-L-6-v2` reranker (2026-10-16). After:
`multilingual-e5-small` hybrid with Portuguese-stemmed BM25 and the
multilingual `mmarco-mMiniLMv2-L12-H384-v1` reranker (2026-10-17):

| Metric | Before | After |
|---|---|---|
| Recall@5 | 0.7250 | 1.0000 |
| Precision@5 | 0.6200 | 0.7650 |
| MRR (retrieval order) | 0.6833 | 0.9625 |
| Precision@1 after reranking | 0.7000 | 1.0000 |
| Mean latency, retrieval / reranking (laptop CPU) | 23.2 / 112.4 ms | 36.2 / 215.1 ms |

| Question -> document language | N | Recall@5 before | Recall@5 after |
|---|---|---|---|
| English -> English | 9 | 1.0000 | 1.0000 |
| English -> Portuguese | 6 | 1.0000 | 1.0000 |
| Portuguese -> English | 14 | 0.2143 | 1.0000 |
| Portuguese -> Portuguese | 11 | 1.0000 | 1.0000 |

The original failure was cross-lingual: the English-trained
`all-MiniLM-L6-v2` retrieved English documents for Portuguese questions in
3 of 14 cases. In the ablation of 30 configurations (3 embedding models x
dense / sparse / hybrid x 3 BM25 stemming options x 2 rerankers), sparse BM25
alone raised that pair to 0.7143-0.8571, multilingual dense embeddings to
0.7857-0.9286, and only the chosen hybrid reached 1.0000. The English
cross-encoder lowered MRR in every multilingual configuration, and the
multilingual one kept or raised it. The configuration was chosen on the same
questions it is measured on, with no held-out set, and the runner-up is one
question behind on Recall@5.

Answers, generator `openai/gpt-oss-120b`, repeated on 2026-10-17 with the
Block 19 retrieval and threshold 0.1 (`docs/evaluation/block19/`; the
Block 18 run is in `docs/evaluation/`):

- Refusal (53 cases, refusing as the positive class): the guardrail alone
  has precision 0.7273 and recall 0.8000 (Block 18: 0.2759 / 0.8000);
  counting the model's abstention sentence as a refusal, recall is 1.0000.
  In-scope questions answered went from 20 to 34 of 40. The two
  out-of-scope questions closest to the corpus pass the guardrail and are
  caught only by the model's abstention.
- Citations: 40/41 answers cite only sources that exist in the retrieved
  context.
- Prompt injection: 1 leak in 5 direct cases and 3 in 5 indirect cases
  (poisoned documents in a separate evaluation collection). In Block 18 the
  direct cases had no leak, but only because the English reranker gave the
  leaking question a low score and the guardrail refused it; with the
  multilingual reranker it reaches the model, which follows the injected
  instruction.
- LLM-as-a-judge on 41 answered questions (judge `openai/gpt-oss-20b`,
  rubric v1): 39 supported and 2 partially supported (both injection
  cases), 40 relevant and 1 irrelevant. On 10 Block 18 answers labelled blind
  by the author, the judge agreed on faithfulness 10/10 and on relevance
  9/10. Neither the judge nor the human labels flagged the successful
  indirect injections as unfaithful, because the injected text is in the
  context; only the deterministic canary check caught them.

Generation prompt v3 (2026-10-18, `docs/prompt-injection.md`,
`docs/evaluation/prompt-v3/`): question and excerpts between delimiters,
explicit rules for orders embedded in the question and for text addressed to
an assistant inside the excerpts. Same 58 cases and retrieval as above:

- Prompt injection leaks: direct 1/5 -> 0/5, indirect 3/5 -> 2/5. The
  prompt was written while looking at these cases, so the drop is optimistic
  for unseen injections.
- No in-scope or out-of-scope decision changed (34 of 40 in-scope questions
  answered); 41/41 answers cite only sources in the context; judge
  faithfulness 41/41 supported.
- English questions answered in English: 2 -> 8 of 18 (manual count). The
  answer-language rule is still ignored in most English cases.
- Llama Prompt Guard 2 (86M, via Groq) was tested as an input classifier and
  rejected: it flags the two classic jailbreaks (0.999) but scores the three
  embedded instructions between 0.0005 and 0.0099.
- `--categories injection_direct injection_indirect` reruns only the 10
  injection cases as a regression check.

Chunking comparison (fixed-size vs. semantic, same 500-character target):
fixed-size produces 167 chunks with low size variance (2817.7); semantic
produces 242 chunks with variance nearly 19 times higher (53654.4), because
it never splits a sentence but also gives no maximum size guarantee (an
HTML sponsor badge block with no sentence punctuation becomes a single
1857-character chunk). Fixed-size is used as the default for indexing.

## Infrastructure

- Docker Compose (`docker-compose.yml`, `Dockerfile`): runs the API, Qdrant,
  and MongoDB together with a single command. The API image installs a
  CPU-only PyTorch build explicitly, since the project never uses a GPU;
  this keeps the image at about 2.15 GB instead of 8.69 GB. See
  `docs/local-setup.md`.
- Observability (`docker-compose.observability.yml`): local Langfuse
  (web, worker, Postgres, ClickHouse, Redis, MinIO), separate from the main
  stack, without a restart policy, and with only the web UI (and MinIO, for
  presigned media URLs) published on `127.0.0.1`.
- Terraform (`infra/terraform`): defines a minimal AWS setup, a VPC with
  public subnets, an ECR repository, and an ECS Fargate service running the
  API. Not applied to a live AWS account by default. Applying it creates
  real, billed resources; read the cost warning and the `apply`/`destroy`
  steps in `infra/terraform/README.md` before running `terraform apply`.
- Kubernetes (`infra/k8s`): a Deployment and a Service for running the same
  API image, as an alternative orchestration demo to ECS. Validated for
  syntax under minikube, and applied against a real k3s cluster running in
  WSL2, confirmed operational via `kubectl` (pods running, service
  reachable) at no cloud cost. See `infra/k8s/README.md`,
  `docs/k3s-setup.md`, and `docs/k3s-deployment-evidence.md`.
- CI (`.github/workflows/ci.yml`): GitHub Actions runs `ruff check`,
  `ruff format --check`, and the full `pytest` suite on every push and pull
  request to `main`. No external service is required, since the test suite
  uses an in-memory Qdrant client, a mocked MongoDB (`mongomock`), and a
  fake LLM instead of live dependencies. A second job, `retrieval-gate`,
  starts Qdrant as a service container, indexes the corpus, and fails if any
  retrieval metric drops more than 0.03 below `data/evaluation/baseline.json`.
  The LLM evaluation with the judge runs in a separate workflow
  (`llm-eval.yml`), only on manual dispatch, and skips cleanly when the
  `GROQ_API_KEY` repository secret is not set.

## Limitations

- The retrieval configuration and the confidence threshold were selected on
  the evaluation questions themselves (no held-out set), so the Block 19
  numbers, including Recall@5 1.0000, are optimistic for unseen questions.
- Chunk size is measured in characters, not tokens, which is an
  approximation of the actual unit the embedding and generation models use.
- The evaluation is small: 58 cases over a 5-document corpus, 41 answers
  judged in the latest run, 10 used to calibrate the judge. It reveals clear patterns (the
  cross-lingual failure, indirect injection) but is too small for
  fine-grained statistical conclusions.
- The LLM judge (`openai/gpt-oss-20b`) shares a model family with the
  generator, so self-preference bias is not ruled out; a judge from another
  vendor (`qwen/qwen3.8-27b`) was tried and rejected because its structured
  output was unreliable on Groq. The calibration sample contained no answer
  rated negatively by either the judge or the author.
- Prompt injection is only partly mitigated: with prompt v3, 2 of 5
  poisoned-document cases still succeed (0 of 5 direct), on a sample of 10
  cases that was also used to write the prompt. There is no structural
  defence against poisoned documents; the impact is limited to the text of
  one answer because the agent is read-only and has no side-effecting tools.
- The answer-language rule is unreliable: 10 of 18 answered English
  questions got a Portuguese answer with prompt v3 (manual count; the
  evaluation has no automated language check).
- The Docker Compose setup runs the API container as root, without restart
  policies or healthchecks, and is meant for local demonstration, not
  production.
- The Terraform module does not provision Qdrant or MongoDB in AWS, only the
  API compute layer; a full cloud deployment would need to extend it.
- The Kubernetes manifests were validated for syntax under minikube. They
  have since been applied to a real k3s cluster (see `docs/k3s-setup.md`),
  but Qdrant and MongoDB still run on the host via Docker Compose, not
  inside the cluster; a fully self-contained cluster deployment would need
  PersistentVolumeClaims and StatefulSets for both.
- Generation depends on the Groq free tier, which has a rate limit; the
  agent enforces its own conservative client-side limit and caches
  responses locally to avoid hitting it during repeated testing.
