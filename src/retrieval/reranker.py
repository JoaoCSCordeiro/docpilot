from functools import lru_cache

from sentence_transformers import CrossEncoder

from src.config import settings
from src.retrieval.retriever import RetrievedChunk


@lru_cache(maxsize=1)
def get_reranker_model() -> CrossEncoder:
    return CrossEncoder(settings.reranker_model_name)


def rerank(query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    if not chunks:
        return []

    model = get_reranker_model()
    pairs = [(query, chunk.text) for chunk in chunks]
    scores = model.predict(pairs)

    reranked = [
        RetrievedChunk(
            source=chunk.source, position=chunk.position, text=chunk.text, score=float(score)
        )
        for chunk, score in zip(chunks, scores)
    ]
    reranked.sort(key=lambda chunk: chunk.score, reverse=True)
    return reranked
