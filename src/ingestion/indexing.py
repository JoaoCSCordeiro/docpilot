from qdrant_client import QdrantClient

from src.ingestion.chunking_fixed import Chunk, chunk_documents_fixed_size
from src.ingestion.loader import Document
from src.retrieval.embeddings import embed_passages, embedding_dimension
from src.retrieval.sparse import embed_sparse_passages
from src.retrieval.vector_store import ensure_collection, index_chunks

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def index_chunks_with_embeddings(
    client: QdrantClient,
    collection_name: str,
    chunks: list[Chunk],
    embedding_model: str | None = None,
    bm25_language: str | None = None,
) -> None:
    texts = [chunk.text for chunk in chunks]
    ensure_collection(client, collection_name, embedding_dimension(embedding_model))
    index_chunks(
        client,
        collection_name,
        chunks,
        embed_passages(texts, embedding_model),
        embed_sparse_passages(texts, bm25_language),
    )


def index_documents(
    client: QdrantClient,
    collection_name: str,
    documents: list[Document],
    recreate: bool = False,
    embedding_model: str | None = None,
    bm25_language: str | None = None,
) -> int:
    if recreate and client.collection_exists(collection_name):
        client.delete_collection(collection_name)

    chunks = chunk_documents_fixed_size(documents, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
    index_chunks_with_embeddings(client, collection_name, chunks, embedding_model, bm25_language)
    return len(chunks)
