#!/bin/sh
set -e

# No compose o Qdrant tem volume e indexa-se a mao; no Azure Container Apps o Qdrant e
# um sidecar efemero e a replica indexa antes de aceitar pedidos.
if [ "${INDEX_ON_STARTUP:-false}" = "true" ]; then
    python scripts/index_if_empty.py
fi

exec "$@"
