import logging
from functools import lru_cache

import redis

from src.config import settings

logger = logging.getLogger(__name__)

# Timeouts curtos: o Redis e uma otimizacao, nao uma dependencia. Se nao responder, o
# pedido segue pelo fallback em vez de ficar pendurado.
_SOCKET_TIMEOUT_SECONDS = 0.5


@lru_cache(maxsize=1)
def get_redis_client() -> redis.Redis | None:
    client = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=_SOCKET_TIMEOUT_SECONDS,
        socket_connect_timeout=_SOCKET_TIMEOUT_SECONDS,
    )
    try:
        client.ping()
    except redis.RedisError as error:
        logger.warning(
            "Redis indisponivel em %s (%s); a usar fallback local", settings.redis_url, error
        )
        return None
    return client
