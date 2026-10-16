import json
import uuid

import pytest
from langfuse import Langfuse
from mcp import Client
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from qdrant_client import QdrantClient

from src.agent import llm as llm_module
from src.agent.graph import REFUSAL_MESSAGE, build_graph, run_agent
from src.agent.llm import GuardedGroqLLM, estimate_groq_cost
from src.agent.rate_limiter import TokenBucket
from src.config import settings
from src.ingestion.chunking_fixed import Chunk
from src.mcp_server.server import build_server
from src.observability import tracing
from src.retrieval.embeddings import embed_texts, embedding_dimension
from src.retrieval.vector_store import ensure_collection, index_chunks

COLLECTION_NAME = "test_tracing_collection"
FASTAPI_TEXT = "FastAPI e uma framework web para construir APIs em Python, baseada em type hints."


class FakeChatGroq:
    model_name = "fake-model"
    temperature = 0.0
    max_tokens = 64

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, prompt: str):
        self.calls += 1
        return type(
            "FakeMessage",
            (),
            {
                "content": "FastAPI e uma framework web.",
                "usage_metadata": {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
            },
        )()


@pytest.fixture
def exporter():
    span_exporter = InMemorySpanExporter()
    client = Langfuse(
        public_key=f"pk-lf-test-{uuid.uuid4()}",
        secret_key="sk-lf-test",
        base_url="http://127.0.0.1:9",
        tracer_provider=TracerProvider(),
        span_exporter=span_exporter,
    )
    tracing.set_langfuse_client(client)
    yield span_exporter
    client.shutdown()


@pytest.fixture
def no_cache(monkeypatch: pytest.MonkeyPatch) -> dict:
    store: dict = {}
    monkeypatch.setattr(llm_module, "get_cached_response", lambda prompt: store.get(prompt))
    monkeypatch.setattr(
        llm_module, "store_response", lambda prompt, response: store.__setitem__(prompt, response)
    )
    monkeypatch.setattr(llm_module, "log_usage", lambda **kwargs: None)
    return store


@pytest.fixture
def populated_client() -> QdrantClient:
    client = QdrantClient(location=":memory:")
    chunks = [
        Chunk(source="fastapi.md", position=0, text=FASTAPI_TEXT),
        Chunk(source="docker.md", position=0, text="Docker Compose orquestra varios containers."),
    ]
    ensure_collection(client, COLLECTION_NAME, embedding_dimension())
    index_chunks(client, COLLECTION_NAME, chunks, embed_texts([chunk.text for chunk in chunks]))
    return client


def _finished_spans(span_exporter: InMemorySpanExporter) -> dict:
    tracing.flush()
    return {span.name: span for span in span_exporter.get_finished_spans()}


def _guarded_llm(chat: FakeChatGroq) -> GuardedGroqLLM:
    return GuardedGroqLLM(chat, TokenBucket(capacity=10, refill_period_seconds=60.0))


def test_tracing_is_a_no_op_without_langfuse_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "langfuse_public_key", "")
    monkeypatch.setattr(settings, "langfuse_secret_key", "")
    monkeypatch.setattr(tracing, "_client", tracing._UNSET)

    with tracing.request_trace("docpilot-query", "api", input={"question": "q"}) as trace:
        with tracing.observation("retrieve", as_type="retriever") as span:
            span.update(output=[])
        trace.update(output={"answer": "a"})
    tracing.flush()

    assert tracing.get_langfuse() is None


def test_answered_query_produces_one_trace_with_a_span_per_node(
    exporter: InMemorySpanExporter, no_cache: dict, populated_client: QdrantClient
) -> None:
    graph = build_graph(
        populated_client,
        _guarded_llm(FakeChatGroq()),
        collection_name=COLLECTION_NAME,
        top_k=2,
    )

    state = run_agent(graph, "Que framework Python e usada para criar APIs web?", entrypoint="api")

    spans = _finished_spans(exporter)
    assert state["is_confident"] is True
    assert {
        "docpilot-query",
        "retrieve",
        "rerank",
        "assess_confidence",
        "generate_answer",
        "llm",
    } <= set(spans)
    assert len({span.context.trace_id for span in spans.values()}) == 1
    root = spans["docpilot-query"]
    assert root.parent is None
    assert root.attributes["langfuse.trace.tags"] == ("api",)
    assert spans["retrieve"].attributes["langfuse.observation.type"] == "retriever"
    assert spans["assess_confidence"].attributes["langfuse.observation.type"] == "guardrail"
    assert spans["llm"].parent.span_id == spans["generate_answer"].context.span_id

    generation = spans["llm"].attributes
    assert generation["langfuse.observation.type"] == "generation"
    assert generation["langfuse.observation.model.name"] == "fake-model"
    assert json.loads(generation["langfuse.observation.usage_details"]) == {
        "input": 120,
        "output": 30,
    }
    assert json.loads(generation["langfuse.observation.cost_details"])["total"] > 0
    assert generation["langfuse.observation.metadata.cache_hit"] == "false"


def test_refused_query_traces_guardrail_decision_without_llm_span(
    exporter: InMemorySpanExporter, no_cache: dict, populated_client: QdrantClient
) -> None:
    chat = FakeChatGroq()
    graph = build_graph(
        populated_client, _guarded_llm(chat), collection_name=COLLECTION_NAME, top_k=2
    )

    state = run_agent(graph, "Qual e a receita tradicional de bacalhau a bras?", entrypoint="cli")

    spans = _finished_spans(exporter)
    assert state["answer"] == REFUSAL_MESSAGE
    assert "refuse" in spans and "llm" not in spans
    guardrail_output = json.loads(
        spans["assess_confidence"].attributes["langfuse.observation.output"]
    )
    assert guardrail_output["is_confident"] is False
    assert guardrail_output["threshold"] == settings.confidence_threshold
    assert chat.calls == 0


def test_cache_hit_is_traced_and_skips_groq(exporter: InMemorySpanExporter, no_cache: dict) -> None:
    chat = FakeChatGroq()
    llm = _guarded_llm(chat)

    first = llm.invoke("prompt repetido")
    second = llm.invoke("prompt repetido")

    assert (first.cache_hit, second.cache_hit) == (False, True)
    assert chat.calls == 1
    tracing.flush()
    generations = [span for span in exporter.get_finished_spans() if span.name == "llm"]
    cache_flags = [
        span.attributes["langfuse.observation.metadata.cache_hit"] for span in generations
    ]
    assert cache_flags == ["false", "true"]
    assert json.loads(generations[1].attributes["langfuse.observation.cost_details"]) == {
        "total": 0.0
    }


def test_estimate_groq_cost_uses_configured_price_per_million(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "groq_price_input_per_million", 0.15)
    monkeypatch.setattr(settings, "groq_price_output_per_million", 0.60)

    cost = estimate_groq_cost(input_tokens=2_000_000, output_tokens=500_000)

    assert cost["input"] == pytest.approx(0.30)
    assert cost["output"] == pytest.approx(0.30)
    assert cost["total"] == pytest.approx(0.60)


class FakeGraph:
    def invoke(self, state: dict) -> dict:
        return {
            "query": state["query"],
            "reranked_chunks": [],
            "confidence": 0.9,
            "is_confident": True,
            "answer": "resposta",
        }


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_mcp_ask_docpilot_is_traced_with_mcp_tag(exporter: InMemorySpanExporter) -> None:
    server = build_server(QdrantClient(location=":memory:"), FakeGraph, collection_name="unused")

    async with Client(server) as client:
        await client.call_tool("ask_docpilot", {"question": "pergunta"})

    spans = _finished_spans(exporter)
    root = spans["docpilot-query"]
    assert root.attributes["langfuse.trace.tags"] == ("mcp",)
    assert json.loads(root.attributes["langfuse.observation.output"])["decision"] == "answered"
