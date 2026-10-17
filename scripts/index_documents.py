import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402
from src.ingestion.indexing import index_documents  # noqa: E402
from src.ingestion.loader import load_documents  # noqa: E402
from src.retrieval.vector_store import get_client  # noqa: E402

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


def main() -> None:
    parser = argparse.ArgumentParser(description="Indexa data/raw no Qdrant (dense + sparse)")
    parser.add_argument("--collection", default=settings.qdrant_collection_name)
    parser.add_argument("--embedding-model", default=settings.embedding_model_name)
    parser.add_argument("--bm25-language", default=settings.bm25_language)
    parser.add_argument(
        "--recreate", action="store_true", help="Apaga a coleccao antes de indexar."
    )
    args = parser.parse_args()

    documents = load_documents(RAW_DIR)
    print(f"Documentos carregados: {len(documents)}")

    client = get_client()
    chunk_count = index_documents(
        client,
        args.collection,
        documents,
        recreate=args.recreate,
        embedding_model=args.embedding_model,
        bm25_language=args.bm25_language,
    )
    print(f"Chunks gerados: {chunk_count}")

    count = client.count(args.collection).count
    print(
        f"Collection '{args.collection}' agora tem {count} pontos "
        f"(embedding {args.embedding_model}, BM25 {args.bm25_language})"
    )


if __name__ == "__main__":
    main()
