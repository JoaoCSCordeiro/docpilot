import pytest
from qdrant_client import QdrantClient

from src.agent.graph import REFUSAL_MESSAGE, build_graph
from src.ingestion.chunking_fixed import Chunk
from src.ingestion.indexing import index_chunks_with_embeddings

COLLECTION_NAME = "test_agent_collection"
FAKE_ANSWER = "FastAPI e uma framework web para construir APIs em Python, baseada em type hints."


class FakeLLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeLLM:
    def invoke(self, prompt: str) -> FakeLLMResponse:
        return FakeLLMResponse(FAKE_ANSWER)


@pytest.fixture
def populated_client() -> QdrantClient:
    client = QdrantClient(location=":memory:")
    chunks = [
        Chunk(
            source="fastapi.md",
            position=0,
            text=FAKE_ANSWER,
        ),
        Chunk(
            source="docker.md",
            position=0,
            text="Docker Compose orquestra multiplos containers a partir de um unico ficheiro.",
        ),
    ]
    index_chunks_with_embeddings(client, COLLECTION_NAME, chunks)
    return client


def test_agent_answers_question_well_covered_by_corpus(populated_client: QdrantClient) -> None:
    graph = build_graph(populated_client, FakeLLM(), collection_name=COLLECTION_NAME, top_k=2)

    result = graph.invoke({"query": "Que framework Python e usada para criar APIs web?"})

    assert result["is_confident"] is True
    assert result["answer"] == FAKE_ANSWER


def test_agent_refuses_question_out_of_domain(populated_client: QdrantClient) -> None:
    graph = build_graph(populated_client, FakeLLM(), collection_name=COLLECTION_NAME, top_k=2)

    result = graph.invoke({"query": "Qual e a receita tradicional de bacalhau a bras?"})

    assert result["is_confident"] is False
    assert result["answer"] == REFUSAL_MESSAGE
