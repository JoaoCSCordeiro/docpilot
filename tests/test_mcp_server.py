import mongomock
import pytest
from httpx import Headers, Request
from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError
from openai import APIConnectionError
from pymongo.errors import ServerSelectionTimeoutError
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
from qdrant_client.models import Distance, PointStruct, VectorParams

from src.mcp_server import server as mcp_server_module
from src.mcp_server.server import MAX_TOP_K, build_server
from src.retrieval.retriever import RetrievedChunk

COLLECTION_NAME = "test_mcp_collection"

RETRIEVED = [
    RetrievedChunk(source="docker.md", position=0, text="Docker Compose orquestra.", score=0.4),
    RetrievedChunk(source="fastapi.md", position=2, text="FastAPI usa Starlette.", score=0.3),
]

ANSWERED_STATE = {
    "query": "Em que se baseia o FastAPI?",
    "retrieved_chunks": RETRIEVED,
    "reranked_chunks": [
        RetrievedChunk(source="fastapi.md", position=2, text="FastAPI usa Starlette.", score=3.1)
    ],
    "confidence": 0.957,
    "is_confident": True,
    "answer": "O FastAPI baseia-se no Starlette.",
}

REFUSED_STATE = {
    **ANSWERED_STATE,
    "reranked_chunks": [
        RetrievedChunk(source="docker.md", position=0, text="Docker Compose orquestra.", score=-6.0)
    ],
    "confidence": 0.002,
    "is_confident": False,
    "answer": "Não tenho informação suficiente.",
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeGraph:
    def __init__(self, state: dict) -> None:
        self.state = state
        self.invocations: list[dict] = []

    def invoke(self, state: dict) -> dict:
        self.invocations.append(state)
        return self.state


class CountingGraphFactory:
    def __init__(self, graph: FakeGraph) -> None:
        self.graph = graph
        self.calls = 0

    def __call__(self) -> FakeGraph:
        self.calls += 1
        return self.graph


class FailingCollection:
    def insert_one(self, document: dict) -> None:
        raise ServerSelectionTimeoutError("mongo down")


def fake_rerank(query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    rescored = [
        RetrievedChunk(source=c.source, position=c.position, text=c.text, score=float(i))
        for i, c in enumerate(chunks)
    ]
    return sorted(rescored, key=lambda chunk: chunk.score, reverse=True)


@pytest.fixture
def fake_retrieval(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    calls: list[tuple] = []

    def fake_retrieve(client, collection_name, query, top_k):
        calls.append((collection_name, query, top_k))
        return RETRIEVED[:top_k]

    monkeypatch.setattr(mcp_server_module, "retrieve", fake_retrieve)
    monkeypatch.setattr(mcp_server_module, "rerank", fake_rerank)
    return calls


def _server(graph_factory=None, query_log=None, client=None):
    return build_server(
        client or QdrantClient(location=":memory:"),
        graph_factory or CountingGraphFactory(FakeGraph(ANSWERED_STATE)),
        collection_name=COLLECTION_NAME,
        query_log=query_log,
    )


@pytest.mark.anyio
async def test_lists_three_tools_with_descriptions_and_bounded_top_k() -> None:
    async with Client(_server()) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert set(tools) == {"search_docs", "ask_docpilot", "list_sources"}
    assert all(tool.description for tool in tools.values())
    top_k_schema = tools["search_docs"].input_schema["properties"]["top_k"]
    assert top_k_schema["minimum"] == 1
    assert top_k_schema["maximum"] == MAX_TOP_K
    assert tools["search_docs"].annotations.read_only_hint is True


@pytest.mark.anyio
async def test_search_docs_returns_reranked_chunks_without_building_graph(
    fake_retrieval: list[tuple],
) -> None:
    graph_factory = CountingGraphFactory(FakeGraph(ANSWERED_STATE))

    async with Client(_server(graph_factory=graph_factory)) as client:
        result = await client.call_tool("search_docs", {"query": "FastAPI", "top_k": 2})

    assert result.is_error is False
    chunks = result.structured_content["chunks"]
    assert [chunk["source"] for chunk in chunks] == ["fastapi.md", "docker.md"]
    assert chunks[0]["text"] == "FastAPI usa Starlette."
    assert 0.0 < result.structured_content["confidence"] < 1.0
    assert fake_retrieval == [(COLLECTION_NAME, "FastAPI", 2)]
    assert graph_factory.calls == 0


@pytest.mark.anyio
@pytest.mark.parametrize("top_k", [0, MAX_TOP_K + 1])
async def test_search_docs_rejects_out_of_range_top_k(
    fake_retrieval: list[tuple], top_k: int
) -> None:
    async with Client(_server()) as client:
        result = await client.call_tool("search_docs", {"query": "FastAPI", "top_k": top_k})

    assert result.is_error is True
    assert fake_retrieval == []


@pytest.mark.anyio
async def test_search_docs_reports_unreachable_qdrant(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_retrieve(*args, **kwargs):
        raise ResponseHandlingException(TimeoutError("timed out"))

    monkeypatch.setattr(mcp_server_module, "retrieve", failing_retrieve)

    async with Client(_server()) as client:
        result = await client.call_tool("search_docs", {"query": "FastAPI"})

    assert result.is_error is True
    assert "not reachable" in result.content[0].text
    assert "docker compose up -d qdrant" in result.content[0].text


@pytest.mark.anyio
async def test_search_docs_reports_missing_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_collection_retrieve(*args, **kwargs):
        raise UnexpectedResponse(404, "Not Found", b"{}", Headers())

    monkeypatch.setattr(mcp_server_module, "retrieve", missing_collection_retrieve)

    async with Client(_server()) as client:
        result = await client.call_tool("search_docs", {"query": "FastAPI"})

    assert result.is_error is True
    assert "index_documents.py" in result.content[0].text


@pytest.mark.anyio
async def test_ask_docpilot_answers_and_saves_trace() -> None:
    graph = FakeGraph(ANSWERED_STATE)
    graph_factory = CountingGraphFactory(graph)
    query_log = mongomock.MongoClient()["test_db"]["query_traces"]

    async with Client(_server(graph_factory=graph_factory, query_log=query_log)) as client:
        first = await client.call_tool("ask_docpilot", {"question": "Em que se baseia o FastAPI?"})
        await client.call_tool("ask_docpilot", {"question": "Outra pergunta"})

    assert first.is_error is False
    assert first.structured_content["decision"] == "answered"
    assert first.structured_content["answer"] == "O FastAPI baseia-se no Starlette."
    assert first.structured_content["sources"] == [
        {"source": "fastapi.md", "position": 2, "score": 3.1}
    ]
    assert graph.invocations[0] == {"query": "Em que se baseia o FastAPI?"}
    assert graph_factory.calls == 1
    assert query_log.count_documents({}) == 2


@pytest.mark.anyio
async def test_ask_docpilot_reports_refusal() -> None:
    graph_factory = CountingGraphFactory(FakeGraph(REFUSED_STATE))

    async with Client(_server(graph_factory=graph_factory)) as client:
        result = await client.call_tool("ask_docpilot", {"question": "Receita de bacalhau?"})

    assert result.structured_content["decision"] == "refused"
    assert (
        result.structured_content["confidence"] < result.structured_content["confidence_threshold"]
    )


@pytest.mark.anyio
async def test_ask_docpilot_still_answers_when_trace_store_is_down() -> None:
    async with Client(_server(query_log=FailingCollection())) as client:
        result = await client.call_tool("ask_docpilot", {"question": "Em que se baseia o FastAPI?"})

    assert result.is_error is False
    assert result.structured_content["decision"] == "answered"


@pytest.mark.anyio
async def test_ask_docpilot_surfaces_graph_factory_error() -> None:
    def missing_key_factory():
        raise ToolError("GROQ_API_KEY is not set on the DocPilot server; ask_docpilot needs it.")

    async with Client(_server(graph_factory=missing_key_factory)) as client:
        result = await client.call_tool("ask_docpilot", {"question": "Em que se baseia o FastAPI?"})

    assert result.is_error is True
    assert "GROQ_API_KEY" in result.content[0].text


class AzureFailingGraph:
    def invoke(self, state: dict) -> dict:
        raise APIConnectionError(
            request=Request("POST", "https://example.openai.azure.com/openai/deployments/x")
        )


@pytest.mark.anyio
async def test_ask_docpilot_reports_azure_openai_failures_as_tool_errors() -> None:
    async with Client(_server(graph_factory=lambda: AzureFailingGraph())) as client:
        result = await client.call_tool("ask_docpilot", {"question": "Em que se baseia o FastAPI?"})

    assert result.is_error is True
    assert "LLM provider request failed (APIConnectionError)" in result.content[0].text


@pytest.mark.anyio
async def test_list_sources_counts_chunks_per_document() -> None:
    qdrant = QdrantClient(location=":memory:")
    qdrant.create_collection(
        COLLECTION_NAME, vectors_config=VectorParams(size=2, distance=Distance.COSINE)
    )
    qdrant.upsert(
        COLLECTION_NAME,
        points=[
            PointStruct(id=i, vector=[1.0, float(i)], payload={"source": source, "position": i})
            for i, source in enumerate(["b.md", "a.md", "b.md"])
        ],
    )

    async with Client(_server(client=qdrant)) as client:
        result = await client.call_tool("list_sources", {})

    assert result.structured_content == {
        "collection": COLLECTION_NAME,
        "total_chunks": 3,
        "sources": [
            {"source": "a.md", "chunk_count": 1},
            {"source": "b.md", "chunk_count": 2},
        ],
    }
