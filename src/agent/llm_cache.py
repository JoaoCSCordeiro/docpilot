import hashlib
import sqlite3
from pathlib import Path

# Ancorado na raiz do repo, nao no cwd: clientes MCP lancam o servidor a partir de
# um diretorio de trabalho arbitrario.
_DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "cache" / "groq_responses.db"


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS responses ("
        "prompt_hash TEXT PRIMARY KEY, response TEXT NOT NULL)"
    )
    return connection


def cache_key(model: str, prompt: str) -> str:
    # O modelo entra na chave: o mesmo prompt enviado ao gerador e ao juiz (ou a outro
    # provider) tem respostas diferentes. Entradas antigas, so com o hash do prompt,
    # deixam de ser encontradas em vez de serem servidas ao modelo errado.
    return hashlib.sha256(f"{model}\n{prompt}".encode("utf-8")).hexdigest()


def get_cached_response(model: str, prompt: str, db_path: Path = _DEFAULT_DB_PATH) -> str | None:
    connection = _connect(db_path)
    try:
        row = connection.execute(
            "SELECT response FROM responses WHERE prompt_hash = ?", (cache_key(model, prompt),)
        ).fetchone()
        return row[0] if row else None
    finally:
        connection.close()


def store_response(
    model: str, prompt: str, response: str, db_path: Path = _DEFAULT_DB_PATH
) -> None:
    connection = _connect(db_path)
    try:
        connection.execute(
            "INSERT OR REPLACE INTO responses (prompt_hash, response) VALUES (?, ?)",
            (cache_key(model, prompt), response),
        )
        connection.commit()
    finally:
        connection.close()
