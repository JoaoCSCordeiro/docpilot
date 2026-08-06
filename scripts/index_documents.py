import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402
from src.ingestion.chunking_fixed import chunk_documents_fixed_size  # noqa: E402
from src.ingestion.loader import load_documents  # noqa: E402
from src.retrieval.embeddings import embed_texts, embedding_dimension  # noqa: E402
from src.retrieval.vector_store import ensure_collection, get_client, index_chunks  # noqa: E402

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def main() -> None:
    documents = load_documents(RAW_DIR)
    print(f"Documentos carregados: {len(documents)}")

    chunks = chunk_documents_fixed_size(documents, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
    print(f"Chunks gerados: {len(chunks)}")

    embeddings = embed_texts([chunk.text for chunk in chunks])

    client = get_client()
    ensure_collection(client, settings.qdrant_collection_name, embedding_dimension())
    index_chunks(client, settings.qdrant_collection_name, chunks, embeddings)

    count = client.count(settings.qdrant_collection_name).count
    print(f"Collection '{settings.qdrant_collection_name}' agora tem {count} pontos")


if __name__ == "__main__":
    main()
