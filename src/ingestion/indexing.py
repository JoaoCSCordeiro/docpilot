from qdrant_client import QdrantClient

from src.ingestion.chunking_fixed import chunk_documents_fixed_size
from src.ingestion.loader import Document
from src.retrieval.embeddings import embed_texts, embedding_dimension
from src.retrieval.vector_store import ensure_collection, index_chunks

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def index_documents(
    client: QdrantClient, collection_name: str, documents: list[Document], recreate: bool = False
) -> int:
    if recreate and client.collection_exists(collection_name):
        client.delete_collection(collection_name)

    chunks = chunk_documents_fixed_size(documents, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
    ensure_collection(client, collection_name, embedding_dimension())
    index_chunks(client, collection_name, chunks, embed_texts([chunk.text for chunk in chunks]))
    return len(chunks)
