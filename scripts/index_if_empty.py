# Corre no arranque do container quando o Qdrant e um sidecar sem disco persistente
# (Azure Container Apps): cada replica nova comeca com o indice vazio. Usa a mesma
# ingestao do scripts/index_documents.py, por isso o indice e igual ao local.
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qdrant_client import QdrantClient  # noqa: E402

from src.config import settings  # noqa: E402
from src.ingestion.indexing import index_documents  # noqa: E402
from src.ingestion.loader import load_documents  # noqa: E402
from src.retrieval.vector_store import get_client  # noqa: E402

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
QDRANT_WAIT_SECONDS = 120


def wait_for_qdrant(client: QdrantClient, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            client.get_collections()
            return
        except Exception as error:
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Qdrant nao respondeu em {timeout_seconds}s") from error
            time.sleep(2)


def collection_point_count(client: QdrantClient, collection_name: str) -> int:
    if not client.collection_exists(collection_name):
        return 0
    return client.count(collection_name).count


def main() -> None:
    client = get_client()
    started = time.perf_counter()
    wait_for_qdrant(client, QDRANT_WAIT_SECONDS)
    collection = settings.qdrant_collection_name

    existing_points = collection_point_count(client, collection)
    if existing_points:
        print(f"Coleccao {collection} ja tem {existing_points} pontos; nada a indexar.")
        return

    documents = load_documents(RAW_DIR)
    chunk_count = index_documents(
        client,
        collection,
        documents,
        embedding_model=settings.embedding_model_name,
        bm25_language=settings.bm25_language,
    )
    print(
        f"Indexados {len(documents)} documentos, {chunk_count} chunks em {collection} "
        f"({time.perf_counter() - started:.1f}s)."
    )


if __name__ == "__main__":
    main()
