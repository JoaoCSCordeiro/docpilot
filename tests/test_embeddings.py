from src.retrieval import embeddings
from src.retrieval.embeddings import embed_texts, embedding_dimension


def test_embed_texts_returns_one_vector_per_text() -> None:
    embeddings = embed_texts(["primeiro texto", "segundo texto", "terceiro texto"])

    assert len(embeddings) == 3


def test_embed_texts_vectors_match_embedding_dimension() -> None:
    embeddings = embed_texts(["algum texto de teste"])

    assert len(embeddings[0]) == embedding_dimension()


def test_embed_texts_similar_sentences_are_closer_than_unrelated_ones() -> None:
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        return dot / (norm_a * norm_b)

    anchor, similar, unrelated = embed_texts(
        [
            "FastAPI e uma framework web para construir APIs em Python.",
            "FastAPI e um framework Python para criar APIs web.",
            "O gato dormiu todo o dia em cima do sofa.",
        ]
    )

    assert cosine_similarity(anchor, similar) > cosine_similarity(anchor, unrelated)


def test_e5_queries_and_passages_get_distinct_prefixes(monkeypatch) -> None:
    encoded: list[list[str]] = []
    monkeypatch.setattr(
        embeddings, "embed_texts", lambda texts, model_name=None: encoded.append(texts) or []
    )

    embeddings.embed_queries(["o que e o Qdrant?"], "intfloat/multilingual-e5-small")
    embeddings.embed_passages(["Qdrant e uma base vetorial."], "intfloat/multilingual-e5-small")

    assert encoded == [["query: o que e o Qdrant?"], ["passage: Qdrant e uma base vetorial."]]


def test_models_without_known_prefixes_embed_text_unchanged(monkeypatch) -> None:
    encoded: list[list[str]] = []
    monkeypatch.setattr(
        embeddings, "embed_texts", lambda texts, model_name=None: encoded.append(texts) or []
    )

    embeddings.embed_queries(["pergunta"], "sentence-transformers/all-MiniLM-L6-v2")

    assert encoded == [["pergunta"]]
