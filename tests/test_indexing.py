import pytest
from qdrant_client import QdrantClient

from src.ingestion.indexing import reindex_document
from src.ingestion.loader import Document
from src.retrieval.vector_store import count_chunks_by_source

COLLECTION_NAME = "reindex_test"


@pytest.fixture
def client() -> QdrantClient:
    return QdrantClient(location=":memory:")


def test_reindex_document_creates_the_collection_on_first_upload(client: QdrantClient) -> None:
    chunk_count = reindex_document(client, COLLECTION_NAME, Document("novo.md", "Texto curto."))

    assert chunk_count == 1
    assert count_chunks_by_source(client, COLLECTION_NAME) == {"novo.md": 1}


def test_reindexing_a_shorter_version_drops_the_old_tail_chunks(client: QdrantClient) -> None:
    long_version = Document("guia.md", " ".join(f"palavra{i}" for i in range(400)))
    reindex_document(client, COLLECTION_NAME, long_version)
    reindex_document(client, COLLECTION_NAME, Document("outro.md", "Outro documento."))
    assert count_chunks_by_source(client, COLLECTION_NAME)["guia.md"] > 1

    reindex_document(client, COLLECTION_NAME, Document("guia.md", "Agora e curto."))

    assert count_chunks_by_source(client, COLLECTION_NAME) == {"guia.md": 1, "outro.md": 1}
