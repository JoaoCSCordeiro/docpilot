import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402
from src.retrieval.reranker import rerank  # noqa: E402
from src.retrieval.retriever import retrieve  # noqa: E402
from src.retrieval.vector_store import get_client  # noqa: E402


def print_results(title: str, chunks) -> None:
    print(f"\n-- {title} --")
    for i, chunk in enumerate(chunks, start=1):
        preview = chunk.text.strip().replace("\n", " ")[:100]
        print(f"{i}. score={chunk.score:.4f} [{chunk.source}#{chunk.position}] {preview!r}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python scripts/query_documents.py \"a tua pergunta aqui\"")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    print(f"QUERY: {query}")

    client = get_client()
    retrieved = retrieve(client, settings.qdrant_collection_name, query, settings.retrieval_top_k)
    print_results("Retrieval (bi-encoder)", retrieved)

    reranked = rerank(query, retrieved)
    print_results("Depois do reranking (cross-encoder)", reranked)


if __name__ == "__main__":
    main()
