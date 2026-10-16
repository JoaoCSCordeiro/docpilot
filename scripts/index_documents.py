import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402
from src.ingestion.indexing import index_documents  # noqa: E402
from src.ingestion.loader import load_documents  # noqa: E402
from src.retrieval.vector_store import get_client  # noqa: E402

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


def main() -> None:
    documents = load_documents(RAW_DIR)
    print(f"Documentos carregados: {len(documents)}")

    client = get_client()
    chunk_count = index_documents(client, settings.qdrant_collection_name, documents)
    print(f"Chunks gerados: {chunk_count}")

    count = client.count(settings.qdrant_collection_name).count
    print(f"Collection '{settings.qdrant_collection_name}' agora tem {count} pontos")


if __name__ == "__main__":
    main()
