import pytest
from qdrant_client import QdrantClient

from src.ingestion.chunking_fixed import Chunk
from src.retrieval.vector_store import (
    chunk_point_id,
    count_chunks_by_source,
    ensure_collection,
    index_chunks,
)

COLLECTION_NAME = "test_collection"
VECTOR_SIZE = 4


@pytest.fixture
def client() -> QdrantClient:
    return QdrantClient(location=":memory:")


def test_ensure_collection_creates_collection_when_missing(client: QdrantClient) -> None:
    assert not client.collection_exists(COLLECTION_NAME)

    ensure_collection(client, COLLECTION_NAME, VECTOR_SIZE)

    assert client.collection_exists(COLLECTION_NAME)


def test_ensure_collection_is_idempotent(client: QdrantClient) -> None:
    ensure_collection(client, COLLECTION_NAME, VECTOR_SIZE)
    ensure_collection(client, COLLECTION_NAME, VECTOR_SIZE)

    assert client.collection_exists(COLLECTION_NAME)


def test_chunk_point_id_is_deterministic_for_same_source_and_position() -> None:
    chunk_a = Chunk(source="doc.md", position=0, text="texto a")
    chunk_b = Chunk(source="doc.md", position=0, text="texto diferente")

    assert chunk_point_id(chunk_a) == chunk_point_id(chunk_b)


def test_chunk_point_id_differs_for_different_position() -> None:
    chunk_a = Chunk(source="doc.md", position=0, text="texto")
    chunk_b = Chunk(source="doc.md", position=1, text="texto")

    assert chunk_point_id(chunk_a) != chunk_point_id(chunk_b)


def test_index_chunks_makes_documents_retrievable_by_id(client: QdrantClient) -> None:
    chunks = [
        Chunk(source="doc.md", position=0, text="primeiro chunk"),
        Chunk(source="doc.md", position=1, text="segundo chunk"),
    ]
    embeddings = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]

    ensure_collection(client, COLLECTION_NAME, VECTOR_SIZE)
    index_chunks(client, COLLECTION_NAME, chunks, embeddings)

    retrieved = client.retrieve(COLLECTION_NAME, ids=[chunk_point_id(chunks[0])])

    assert len(retrieved) == 1
    assert retrieved[0].payload["text"] == "primeiro chunk"
    assert retrieved[0].payload["source"] == "doc.md"


def test_index_chunks_search_returns_most_similar_chunk_first(client: QdrantClient) -> None:
    chunks = [
        Chunk(source="doc.md", position=0, text="sobre gatos"),
        Chunk(source="doc.md", position=1, text="sobre cassetes"),
    ]
    embeddings = [[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]]

    ensure_collection(client, COLLECTION_NAME, VECTOR_SIZE)
    index_chunks(client, COLLECTION_NAME, chunks, embeddings)

    results = client.query_points(COLLECTION_NAME, query=[0.9, 0.1, 0.0, 0.0], limit=1).points

    assert results[0].payload["text"] == "sobre gatos"


def test_index_chunks_rejects_mismatched_lengths(client: QdrantClient) -> None:
    chunks = [Chunk(source="doc.md", position=0, text="chunk")]
    embeddings = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]

    ensure_collection(client, COLLECTION_NAME, VECTOR_SIZE)

    with pytest.raises(ValueError):
        index_chunks(client, COLLECTION_NAME, chunks, embeddings)


def test_count_chunks_by_source_walks_every_scroll_page(client: QdrantClient) -> None:
    chunks = [Chunk(source="b.md", position=i, text=f"b{i}") for i in range(3)]
    chunks.append(Chunk(source="a.md", position=0, text="a0"))
    ensure_collection(client, COLLECTION_NAME, VECTOR_SIZE)
    index_chunks(client, COLLECTION_NAME, chunks, [[1.0, 0.0, 0.0, 0.0]] * len(chunks))

    counts = count_chunks_by_source(client, COLLECTION_NAME, page_size=2)

    assert counts == {"a.md": 1, "b.md": 3}
