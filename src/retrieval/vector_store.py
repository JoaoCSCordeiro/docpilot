import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    Modifier,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from src.config import settings
from src.ingestion.chunking_fixed import Chunk

# Namespace fixo para gerar UUIDs deterministicos a partir de (source, position),
# tornando a indexacao idempotente: reindexar o mesmo chunk atualiza o ponto
# existente em vez de duplicar.
_CHUNK_ID_NAMESPACE = uuid.UUID("6f6f0f2e-6c4c-4e3e-8f8e-1c9a2f6d5b7a")

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


def get_client() -> QdrantClient:
    return QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)


def ensure_collection(client: QdrantClient, collection_name: str, vector_size: int) -> None:
    if client.collection_exists(collection_name):
        return
    client.create_collection(
        collection_name=collection_name,
        vectors_config={
            DENSE_VECTOR_NAME: VectorParams(size=vector_size, distance=Distance.COSINE)
        },
        # O IDF do BM25 e calculado pelo Qdrant sobre a coleccao; o fastembed so envia o TF.
        sparse_vectors_config={SPARSE_VECTOR_NAME: SparseVectorParams(modifier=Modifier.IDF)},
    )


def chunk_point_id(chunk: Chunk) -> str:
    return str(uuid.uuid5(_CHUNK_ID_NAMESPACE, f"{chunk.source}:{chunk.position}"))


def index_chunks(
    client: QdrantClient,
    collection_name: str,
    chunks: list[Chunk],
    dense_embeddings: list[list[float]],
    sparse_embeddings: list[SparseVector],
) -> None:
    if not len(chunks) == len(dense_embeddings) == len(sparse_embeddings):
        raise ValueError("chunks e embeddings devem ter o mesmo tamanho")

    points = [
        PointStruct(
            id=chunk_point_id(chunk),
            vector={DENSE_VECTOR_NAME: dense, SPARSE_VECTOR_NAME: sparse},
            payload={"source": chunk.source, "position": chunk.position, "text": chunk.text},
        )
        for chunk, dense, sparse in zip(chunks, dense_embeddings, sparse_embeddings)
    ]
    client.upsert(collection_name=collection_name, points=points)


def delete_chunks_by_source(client: QdrantClient, collection_name: str, source: str) -> None:
    # Os IDs sao uuid5(source:position): reindexar um documento que encolheu sobrescreve
    # as primeiras posicoes mas deixava as antigas do fim no indice.
    client.delete(
        collection_name,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="source", match=MatchValue(value=source))])
        ),
    )


def count_chunks_by_source(
    client: QdrantClient, collection_name: str, page_size: int = 256
) -> dict[str, int]:
    # Scroll em vez da Facet API: a facet exige um payload index em `source`, que a
    # coleccao nao tem; para algumas centenas de pontos o scroll e suficiente.
    counts: dict[str, int] = {}
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name,
            limit=page_size,
            offset=offset,
            with_payload=["source"],
            with_vectors=False,
        )
        for point in points:
            source = point.payload["source"]
            counts[source] = counts.get(source, 0) + 1
        if offset is None:
            return dict(sorted(counts.items()))
