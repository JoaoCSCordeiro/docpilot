from functools import lru_cache

from sentence_transformers import CrossEncoder
from torch import nn

from src.config import settings
from src.retrieval.retriever import RetrievedChunk


@lru_cache(maxsize=4)
def get_reranker_model(model_name: str | None = None) -> CrossEncoder:
    # Sem activation explicita, o sentence-transformers aplica sigmoid aos modelos cujo
    # config nao a define (ex: mmarco-mMiniLMv2) e devolve logits aos outros (ms-marco).
    # O guardrail espera sempre logits, por isso fixa-se Identity para todos.
    return CrossEncoder(
        model_name or settings.reranker_model_name, default_activation_function=nn.Identity()
    )


def rerank(
    query: str, chunks: list[RetrievedChunk], model_name: str | None = None
) -> list[RetrievedChunk]:
    if not chunks:
        return []

    model = get_reranker_model(model_name)
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
