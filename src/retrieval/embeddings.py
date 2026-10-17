from functools import lru_cache

from sentence_transformers import SentenceTransformer

from src.config import settings

# Os modelos e5 foram treinados com estes prefixos e degradam sem eles; os restantes
# modelos usam o texto tal como esta.
QUERY_PASSAGE_PREFIXES: dict[str, tuple[str, str]] = {
    "intfloat/multilingual-e5-small": ("query: ", "passage: "),
}


@lru_cache(maxsize=4)
def get_embedding_model(model_name: str | None = None) -> SentenceTransformer:
    return SentenceTransformer(model_name or settings.embedding_model_name)


def embed_texts(texts: list[str], model_name: str | None = None) -> list[list[float]]:
    model = get_embedding_model(model_name)
    return model.encode(texts, convert_to_numpy=True).tolist()


def _prefixes(model_name: str | None) -> tuple[str, str]:
    return QUERY_PASSAGE_PREFIXES.get(model_name or settings.embedding_model_name, ("", ""))


def embed_queries(queries: list[str], model_name: str | None = None) -> list[list[float]]:
    query_prefix, _ = _prefixes(model_name)
    return embed_texts([query_prefix + query for query in queries], model_name)


def embed_passages(passages: list[str], model_name: str | None = None) -> list[list[float]]:
    _, passage_prefix = _prefixes(model_name)
    return embed_texts([passage_prefix + passage for passage in passages], model_name)


def embedding_dimension(model_name: str | None = None) -> int:
    return get_embedding_model(model_name).get_sentence_embedding_dimension()
