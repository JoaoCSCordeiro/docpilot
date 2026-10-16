from dataclasses import dataclass

from qdrant_client import QdrantClient

from src.config import settings
from src.retrieval.embeddings import embed_texts
from src.retrieval.vector_store import get_client


@dataclass
class RetrievedChunk:
    source: str
    position: int
    text: str
    score: float

    def summary(self) -> dict:
        return {"source": self.source, "position": self.position, "score": self.score}


def retrieve(
    client: QdrantClient, collection_name: str, query: str, top_k: int
) -> list[RetrievedChunk]:
    query_embedding = embed_texts([query])[0]
    results = client.query_points(collection_name, query=query_embedding, limit=top_k).points
    return [
        RetrievedChunk(
            source=point.payload["source"],
            position=point.payload["position"],
            text=point.payload["text"],
            score=point.score,
        )
        for point in results
    ]


def retrieve_with_defaults(query: str) -> list[RetrievedChunk]:
    client = get_client()
    return retrieve(client, settings.qdrant_collection_name, query, settings.retrieval_top_k)
