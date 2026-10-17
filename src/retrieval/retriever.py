from dataclasses import dataclass, field

from qdrant_client import QdrantClient
from qdrant_client.models import Prefetch, Rrf, RrfQuery

from src.config import settings
from src.retrieval.embeddings import embed_queries
from src.retrieval.sparse import embed_sparse_query
from src.retrieval.vector_store import DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME, get_client

RETRIEVAL_MODES = ("dense", "sparse", "hybrid")
# Cada ramo do hybrid traz mais candidatos do que o top_k final, para a fusao RRF poder
# promover chunks que so um dos ramos coloca no topo.
HYBRID_PREFETCH_LIMIT = 20
# Com o k=2 do Qdrant, um chunk so no topo do dense e outro so no topo do sparse empatam
# exatamente (1/2 = 1/2), e o Qdrant devolve os empates por uma ordem que muda entre
# coleccoes com os mesmos dados. Um peso ligeiramente menor no sparse desempata a favor
# do dense; a diferenca minima entre somas RRF distintas (ranks < 20) e ~4.9e-5, muito acima
# do desvio maximo deste peso (5e-7), por isso nao altera nenhuma ordem que nao fosse empate.
SPARSE_TIE_BREAK_WEIGHT = 0.999999


@dataclass
class RetrievedChunk:
    source: str
    position: int
    text: str
    score: float

    def summary(self) -> dict:
        return {"source": self.source, "position": self.position, "score": self.score}


@dataclass(frozen=True)
class RetrievalConfig:
    mode: str = field(default_factory=lambda: settings.retrieval_mode)
    embedding_model: str = field(default_factory=lambda: settings.embedding_model_name)
    bm25_language: str = field(default_factory=lambda: settings.bm25_language)

    def __post_init__(self) -> None:
        if self.mode not in RETRIEVAL_MODES:
            raise ValueError(f"modo de retrieval desconhecido: {self.mode!r}")


def _query_points(
    client: QdrantClient, collection_name: str, query: str, top_k: int, config: RetrievalConfig
):
    if config.mode == "dense":
        return client.query_points(
            collection_name,
            query=embed_queries([query], config.embedding_model)[0],
            using=DENSE_VECTOR_NAME,
            limit=top_k,
        )
    if config.mode == "sparse":
        return client.query_points(
            collection_name,
            query=embed_sparse_query(query, config.bm25_language),
            using=SPARSE_VECTOR_NAME,
            limit=top_k,
        )
    return client.query_points(
        collection_name,
        prefetch=[
            Prefetch(
                query=embed_queries([query], config.embedding_model)[0],
                using=DENSE_VECTOR_NAME,
                limit=HYBRID_PREFETCH_LIMIT,
            ),
            Prefetch(
                query=embed_sparse_query(query, config.bm25_language),
                using=SPARSE_VECTOR_NAME,
                limit=HYBRID_PREFETCH_LIMIT,
            ),
        ],
        query=RrfQuery(rrf=Rrf(weights=[1.0, SPARSE_TIE_BREAK_WEIGHT])),
        limit=top_k,
    )


def retrieve(
    client: QdrantClient,
    collection_name: str,
    query: str,
    top_k: int,
    config: RetrievalConfig | None = None,
) -> list[RetrievedChunk]:
    results = _query_points(client, collection_name, query, top_k, config or RetrievalConfig())
    return [
        RetrievedChunk(
            source=point.payload["source"],
            position=point.payload["position"],
            text=point.payload["text"],
            score=point.score,
        )
        for point in results.points
    ]


def retrieve_with_defaults(query: str) -> list[RetrievedChunk]:
    client = get_client()
    return retrieve(client, settings.qdrant_collection_name, query, settings.retrieval_top_k)
