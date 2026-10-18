import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from azure.core.exceptions import ResourceExistsError  # noqa: E402
from azure.storage.blob import BlobServiceClient  # noqa: E402

from src.retrieval.vector_store import count_chunks_by_source, get_client  # noqa: E402

# Connection string publica e fixa do Azurite (documentada pela Microsoft), nao e um
# segredo: so funciona contra o emulador local.
AZURITE_CONNECTION_STRING = "UseDevelopmentStorage=true"
CONTAINER_NAME = "docs"


def chunks_for_source(collection: str, source: str) -> int:
    client = get_client()
    if not client.collection_exists(collection):
        return 0
    return count_chunks_by_source(client, collection).get(source, 0)


def point_count(collection: str) -> int:
    client = get_client()
    return client.count(collection).count if client.collection_exists(collection) else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Envia um documento para o Azurite e mede ate a Azure Function o indexar"
    )
    parser.add_argument("file", type=Path)
    parser.add_argument("--collection", default="docpilot_v2_azure_demo")
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    source = args.file.name
    before = chunks_for_source(args.collection, source)
    print(
        f"Antes: {before} chunks de {source}, {point_count(args.collection)} pontos em "
        f"{args.collection}"
    )

    service = BlobServiceClient.from_connection_string(AZURITE_CONNECTION_STRING)
    try:
        service.create_container(CONTAINER_NAME)
    except ResourceExistsError:
        pass
    uploaded_at = time.monotonic()
    service.get_blob_client(CONTAINER_NAME, source).upload_blob(
        args.file.read_bytes(), overwrite=True
    )
    print(f"Upload de {source} para {CONTAINER_NAME}/ feito; a aguardar a function...")

    # Deteta a mudanca na contagem: reenviar um ficheiro com o mesmo numero de chunks
    # nao seria detetado, por isso a demonstracao usa um documento novo na coleccao.
    while time.monotonic() - uploaded_at < args.timeout:
        after = chunks_for_source(args.collection, source)
        if after != before:
            elapsed = time.monotonic() - uploaded_at
            print(
                f"Depois: {after} chunks de {source}, {point_count(args.collection)} pontos "
                f"em {args.collection} ({elapsed:.1f}s desde o upload)"
            )
            return
        time.sleep(1)
    raise SystemExit(f"A function nao indexou {source} em {args.timeout:.0f}s")


if __name__ == "__main__":
    main()
