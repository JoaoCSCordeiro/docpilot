import hashlib
import logging
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import redis

from src.agent.redis_client import get_redis_client
from src.config import settings

logger = logging.getLogger(__name__)

# Ancorado na raiz do repo, nao no cwd: clientes MCP lancam o servidor a partir de
# um diretorio de trabalho arbitrario.
_DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "cache" / "groq_responses.db"
REDIS_KEY_PREFIX = "docpilot:llm:"


def cache_key(model: str, prompt: str) -> str:
    # O modelo entra na chave: o mesmo prompt enviado ao gerador e ao juiz (ou a outro
    # provider) tem respostas diferentes. Entradas antigas, so com o hash do prompt,
    # deixam de ser encontradas em vez de serem servidas ao modelo errado.
    return hashlib.sha256(f"{model}\n{prompt}".encode("utf-8")).hexdigest()


class ResponseCache(Protocol):
    def get(self, model: str, prompt: str) -> str | None: ...

    def set(self, model: str, prompt: str, response: str) -> None: ...


class SQLiteResponseCache:
    def __init__(self, db_path: Path = _DEFAULT_DB_PATH) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS responses ("
            "prompt_hash TEXT PRIMARY KEY, response TEXT NOT NULL)"
        )
        return connection

    def get(self, model: str, prompt: str) -> str | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT response FROM responses WHERE prompt_hash = ?", (cache_key(model, prompt),)
            ).fetchone()
            return row[0] if row else None
        finally:
            connection.close()

    def set(self, model: str, prompt: str, response: str) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "INSERT OR REPLACE INTO responses (prompt_hash, response) VALUES (?, ?)",
                (cache_key(model, prompt), response),
            )
            connection.commit()
        finally:
            connection.close()


class RedisResponseCache:
    def __init__(
        self, client: redis.Redis, ttl_seconds: int = 0, fallback: ResponseCache | None = None
    ) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds
        self._fallback = fallback

    def get(self, model: str, prompt: str) -> str | None:
        try:
            return self._client.get(REDIS_KEY_PREFIX + cache_key(model, prompt))
        except redis.RedisError as error:
            logger.warning("Leitura da cache Redis falhou (%s); a usar fallback", error)
            return self._fallback.get(model, prompt) if self._fallback else None

    def set(self, model: str, prompt: str, response: str) -> None:
        try:
            self._client.set(
                REDIS_KEY_PREFIX + cache_key(model, prompt),
                response,
                ex=self._ttl_seconds or None,
            )
        except redis.RedisError as error:
            logger.warning("Escrita na cache Redis falhou (%s); a usar fallback", error)
            if self._fallback:
                self._fallback.set(model, prompt, response)


@lru_cache(maxsize=1)
def get_response_cache() -> ResponseCache:
    sqlite_cache = SQLiteResponseCache()
    if settings.llm_cache_backend != "redis":
        return sqlite_cache
    client = get_redis_client()
    if client is None:
        return sqlite_cache
    return RedisResponseCache(client, settings.llm_cache_ttl_seconds, fallback=sqlite_cache)


def get_cached_response(model: str, prompt: str) -> str | None:
    return get_response_cache().get(model, prompt)


def store_response(model: str, prompt: str, response: str) -> None:
    get_response_cache().set(model, prompt, response)
