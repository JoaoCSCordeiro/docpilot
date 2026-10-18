import logging
import sys
import time
from pathlib import Path

import azure.functions as func

# O func start corre a partir de functions/; o pacote src/ esta na raiz do repositorio.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402
from src.ingestion.indexing import reindex_document  # noqa: E402
from src.ingestion.loader import SUPPORTED_EXTENSIONS, Document  # noqa: E402
from src.retrieval.vector_store import get_client  # noqa: E402

app = func.FunctionApp()


@app.blob_trigger(arg_name="blob", path="docs/{name}", connection="AzureWebJobsStorage")
def reindex_uploaded_document(blob: func.InputStream) -> None:
    # blob.name inclui o container ("docs/guia.md"); a source fica igual a do loader.
    source = blob.name.split("/", 1)[1]
    if Path(source).suffix.lower() not in SUPPORTED_EXTENSIONS:
        logging.info("Ignorado %s: extensao nao suportada", source)
        return

    started = time.perf_counter()
    document = Document(source=source, content=blob.read().decode("utf-8"))
    chunk_count = reindex_document(get_client(), settings.qdrant_collection_name, document)
    logging.info(
        "Reindexado %s: %d chunks em %s (%.1fs)",
        source,
        chunk_count,
        settings.qdrant_collection_name,
        time.perf_counter() - started,
    )
