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
- Retrieval (`src/retrieval`): generates embeddings with `sentence-transformers`
  (local, CPU, no external API), indexes them in Qdrant, and retrieves the
  top-k most similar chunks for a query. A cross-encoder reranks the
  candidates before they reach the agent.
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
  embed, index) against `data/raw`.
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

Full methodology and per-case results in `docs/evaluation/README.md` (answer
evaluation, Block 18) and `docs/evaluation-results.md` (original retrieval
evaluation). Numbers below come from one run on 2026-10-16 with a 58-case
dataset: 40 in-scope questions (25 Portuguese, 15 English), 8 out-of-scope
questions, and 10 prompt injection cases.

Retrieval, 40 in-scope questions, top 5:

| Metric | Value |
|---|---|
| Recall@5 | 0.7250 |
| Precision@5 | 0.6200 |
| MRR | 0.6833 |
| Precision@1 (before / after reranking) | 0.6500 / 0.7000 |

| Question -> document language | N | Recall@5 |
|---|---|---|
| English -> English | 9 | 1.0000 |
| English -> Portuguese | 6 | 1.0000 |
| Portuguese -> English | 14 | 0.2143 |
| Portuguese -> Portuguese | 11 | 1.0000 |

The retrieval failure is cross-lingual and one-directional: Portuguese
questions about English documents reach 0.2143, while English questions
retrieve Portuguese documents without loss. The embedding model
(`all-MiniLM-L6-v2`) is predominantly trained on English. Reranking improves
precision@1 within the retrieved candidates but cannot recover a document
that never reached the top-k.

Answers, generator `openai/gpt-oss-120b`:

- Refusal (53 cases, refusing as the positive class): the confidence
  guardrail alone has precision 0.2759 and recall 0.8000; counting the
  model's abstention sentence as a refusal, recall is 1.0000. The guardrail
  refuses 8 in-scope questions whose document was retrieved, and a threshold
  sweep shows the current threshold (0.5) is not justified by these data; it
  is kept until the reranker change in the next block.
- Citations: 26/26 answers cite sources that exist in the retrieved context.
- Prompt injection: no leak in 5 direct cases; in 5 indirect cases (poisoned
  documents in a separate evaluation collection), the injected instruction
  succeeded in 3, including a canary string and a malicious URL in the
  answer.
- LLM-as-a-judge on 25 questions (judge `openai/gpt-oss-20b`, rubric v1):
  all 25 answers rated supported by the context and relevant. On 10 answers
  labelled blind by the author, the judge agreed on faithfulness 10/10 and on
  relevance 9/10. Neither the judge nor the human labels flagged the three
  successful injections as unfaithful, because the injected text is in the
  context; only the deterministic canary check caught them.

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

- Retrieval degrades substantially in cross-lingual scenarios (Portuguese
  queries against English documents); see Evaluation Results above.
- Chunk size is measured in characters, not tokens, which is an
  approximation of the actual unit the embedding and generation models use.
- The evaluation is small: 58 cases over a 5-document corpus, 25 answers
  judged, 10 used to calibrate the judge. It reveals clear patterns (the
  cross-lingual failure, indirect injection) but is too small for
  fine-grained statistical conclusions.
- The LLM judge (`openai/gpt-oss-20b`) shares a model family with the
  generator, so self-preference bias is not ruled out; a judge from another
  vendor (`qwen/qwen3.8-27b`) was tried and rejected because its structured
  output was unreliable on Groq. The calibration sample contained no answer
  rated negatively by either the judge or the author.
- Indirect prompt injection is not mitigated: the generation prompt tells the
  model to treat retrieved text as data, and 3 of 5 poisoned-document cases
  still succeeded.
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
