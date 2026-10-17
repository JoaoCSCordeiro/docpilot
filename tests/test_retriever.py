import pytest
from qdrant_client import QdrantClient

from src.ingestion.chunking_fixed import Chunk
from src.ingestion.indexing import index_chunks_with_embeddings
from src.retrieval.retriever import RetrievalConfig, retrieve

COLLECTION_NAME = "test_retriever_collection"


@pytest.fixture
def populated_client() -> QdrantClient:
    client = QdrantClient(location=":memory:")
    chunks = [
        Chunk(
            source="fastapi.md",
            position=0,
            text="FastAPI e uma framework web para construir APIs em Python.",
        ),
        Chunk(source="gatos.md", position=0, text="O gato dormiu todo o dia em cima do sofa."),
        Chunk(
            source="docker.md",
            position=0,
            text="Docker Compose permite orquestrar multiplos containers.",
        ),
    ]
    index_chunks_with_embeddings(client, COLLECTION_NAME, chunks)
    return client


def test_retrieve_returns_top_k_chunks_ordered_by_score(
    populated_client: QdrantClient,
) -> None:
    results = retrieve(
        populated_client,
        COLLECTION_NAME,
        "Que framework Python e usada para criar APIs web?",
        top_k=2,
    )

    assert len(results) == 2
    assert results[0].source == "fastapi.md"
    assert results[0].score >= results[1].score


def test_retrieve_respects_top_k(populated_client: QdrantClient) -> None:
    results = retrieve(populated_client, COLLECTION_NAME, "containers", top_k=1)

    assert len(results) == 1


def test_retrieve_includes_expected_fields(populated_client: QdrantClient) -> None:
    results = retrieve(populated_client, COLLECTION_NAME, "sofa e gato", top_k=1)

    result = results[0]
    assert result.source == "gatos.md"
    assert result.position == 0
    assert "gato" in result.text
    assert isinstance(result.score, float)


def test_retrieval_config_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError):
        RetrievalConfig(mode="keyword")


def test_sparse_mode_matches_exact_rare_term(populated_client: QdrantClient) -> None:
    results = retrieve(
        populated_client, COLLECTION_NAME, "Compose", top_k=1, config=RetrievalConfig("sparse")
    )

    assert results[0].source == "docker.md"


def test_sparse_mode_returns_nothing_without_shared_terms(populated_client: QdrantClient) -> None:
    results = retrieve(
        populated_client, COLLECTION_NAME, "xylofone", top_k=3, config=RetrievalConfig("sparse")
    )

    assert results == []


def test_hybrid_mode_fuses_dense_and_sparse_results(populated_client: QdrantClient) -> None:
    results = retrieve(
        populated_client,
        COLLECTION_NAME,
        "Que framework Python e usada para criar APIs web?",
        top_k=2,
        config=RetrievalConfig("hybrid"),
    )

    assert len(results) == 2
    assert results[0].source == "fastapi.md"
