from functools import lru_cache

from sentence_transformers import SentenceTransformer

from src.config import settings


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(settings.embedding_model_name)


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_embedding_model()
    return model.encode(texts, convert_to_numpy=True).tolist()


def embedding_dimension() -> int:
    return get_embedding_model().get_sentence_embedding_dimension()
