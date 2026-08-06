import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from src.config import settings
from src.ingestion.chunking_fixed import Chunk

# Namespace fixo para gerar UUIDs deterministicos a partir de (source, position),
# tornando a indexacao idempotente: reindexar o mesmo chunk atualiza o ponto
# existente em vez de duplicar.
_CHUNK_ID_NAMESPACE = uuid.UUID("6f6f0f2e-6c4c-4e3e-8f8e-1c9a2f6d5b7a")


def get_client() -> QdrantClient:
    return QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)


def ensure_collection(client: QdrantClient, collection_name: str, vector_size: int) -> None:
    if client.collection_exists(collection_name):
        return
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def chunk_point_id(chunk: Chunk) -> str:
    return str(uuid.uuid5(_CHUNK_ID_NAMESPACE, f"{chunk.source}:{chunk.position}"))


def index_chunks(
    client: QdrantClient,
    collection_name: str,
    chunks: list[Chunk],
    embeddings: list[list[float]],
) -> None:
    if len(chunks) != len(embeddings):
        raise ValueError("chunks e embeddings devem ter o mesmo tamanho")

    points = [
        PointStruct(
            id=chunk_point_id(chunk),
            vector=embedding,
            payload={"source": chunk.source, "position": chunk.position, "text": chunk.text},
        )
        for chunk, embedding in zip(chunks, embeddings)
    ]
    client.upsert(collection_name=collection_name, points=points)
