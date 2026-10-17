from functools import lru_cache

from fastembed.common.utils import remove_non_alphanumeric
from fastembed.sparse.bm25 import Bm25
from qdrant_client.models import SparseVector

from src.config import settings

BM25_MODEL_NAME = "Qdrant/bm25"
# "none" desliga o stemming e as stopwords: com corpus misto PT/EN, um stemmer de uma
# so lingua estraga os termos da outra.
NO_STEMMING = "none"


def _build_bm25(language: str, avg_len: float = 256.0) -> Bm25:
    if language == NO_STEMMING:
        return Bm25(BM25_MODEL_NAME, avg_len=avg_len, disable_stemmer=True)
    return Bm25(BM25_MODEL_NAME, avg_len=avg_len, language=language)


@lru_cache(maxsize=4)
def get_query_bm25(language: str) -> Bm25:
    # A query do BM25 nao usa avg_len (todos os termos valem 1.0), por isso uma instancia
    # por lingua serve qualquer coleccao.
    return _build_bm25(language)


def _to_sparse_vector(embedding) -> SparseVector:
    return SparseVector(indices=embedding.indices.tolist(), values=embedding.values.tolist())


def average_token_count(passages: list[str], language: str) -> float:
    # O |d| da formula do fastembed conta os tokens depois das stopwords e do stemming;
    # a versao 0.9 nao expoe isso publicamente, dai o uso de _stem.
    bm25 = get_query_bm25(language)
    lengths = [
        len(bm25._stem(bm25.tokenizer.tokenize(remove_non_alphanumeric(passage))))
        for passage in passages
    ]
    return sum(lengths) / len(lengths) if lengths else 1.0


def embed_sparse_passages(passages: list[str], language: str | None = None) -> list[SparseVector]:
    effective_language = language or settings.bm25_language
    # O avg_len por omissao (256) e o de documentos longos; os chunks deste corpus sao muito
    # mais curtos, e um avg_len errado desequilibra a normalizacao por comprimento.
    bm25 = _build_bm25(
        effective_language, avg_len=average_token_count(passages, effective_language)
    )
    return [_to_sparse_vector(embedding) for embedding in bm25.embed(passages)]


def embed_sparse_query(query: str, language: str | None = None) -> SparseVector:
    bm25 = get_query_bm25(language or settings.bm25_language)
    return _to_sparse_vector(next(iter(bm25.query_embed(query))))
