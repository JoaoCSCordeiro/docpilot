import math

from src.config import settings
from src.retrieval.retriever import RetrievedChunk


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def confidence_score(chunks: list[RetrievedChunk]) -> float:
    if not chunks:
        return 0.0
    return sigmoid(chunks[0].score)


def is_confident(chunks: list[RetrievedChunk], threshold: float | None = None) -> bool:
    effective_threshold = settings.confidence_threshold if threshold is None else threshold
    return confidence_score(chunks) >= effective_threshold
