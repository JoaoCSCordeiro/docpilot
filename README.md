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
                                                              v
                                          FastAPI endpoint -> MongoDB trace log
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
- Evaluation (`src/evaluation`): recall@k and precision@k against a manually
  annotated question/answer dataset, plus a chunking strategy comparison.

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
- `scripts/run_evaluation.py`: runs the QA dataset (`data/evaluation/qa_dataset.json`)
  against the retrieval pipeline and prints recall/precision metrics.

Every answer, confident or refused, is logged as a document in MongoDB
(collection `query_traces`), inspectable with `mongosh` or Compass; see
`docs/mongodb-query-log.md` for the schema and the reasoning behind using
MongoDB for this specific case.

## Evaluation Results

Full results and methodology in `docs/evaluation-results.md`,
`docs/chunking-comparison.md`, and `docs/reranking-notes.md`. Summary,
measured against the real corpus and a 25-question dataset:

| Metric | Value |
|---|---|
| Recall@5 | 0.5600 |
| Precision@5 | 0.4240 |
| Precision@1 (before reranking) | 0.4400 |
| Precision@1 (after reranking) | 0.5200 |

The main finding is a cross-lingual retrieval failure: recall@5 is 1.0000 for
questions about Portuguese-language documents (11 questions) but only 0.2143
for questions about English-language documents (14 questions), all asked in
Portuguese. The embedding model used (`all-MiniLM-L6-v2`) is predominantly
trained on English and does not reliably place semantically equivalent
Portuguese and English text close together in vector space. Reranking
improves precision@1 within the already-retrieved candidates but cannot
recover a document that never reached the top-k in the first place, since it
only reorders what the retriever already returned.

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
  fake LLM instead of live dependencies.

## Limitations

- Retrieval degrades substantially in cross-lingual scenarios (Portuguese
  queries against English documents); see Evaluation Results above.
- Chunk size is measured in characters, not tokens, which is an
  approximation of the actual unit the embedding and generation models use.
- The evaluation dataset has 25 questions, enough to reveal a clear pattern
  like the cross-lingual failure, but too small for fine-grained statistical
  conclusions on other dimensions.
- The evaluation measures retrieval quality only; it does not score the
  correctness of the final generated answer.
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
