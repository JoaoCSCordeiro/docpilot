from contextlib import contextmanager
from typing import Any, Iterator

from langfuse import Langfuse, propagate_attributes

from src.config import settings


class _NoOpObservation:
    def update(self, **kwargs: Any) -> None:
        pass


_NO_OP_OBSERVATION = _NoOpObservation()
_UNSET = object()
_client: Any = _UNSET


def _build_client_from_settings() -> Langfuse | None:
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_base_url,
    )


def get_langfuse() -> Langfuse | None:
    global _client
    if _client is _UNSET:
        _client = _build_client_from_settings()
    return _client


def set_langfuse_client(client: Langfuse | None) -> None:
    global _client
    _client = client


@contextmanager
def observation(name: str, as_type: str = "span", **attributes: Any) -> Iterator[Any]:
    client = get_langfuse()
    if client is None:
        yield _NO_OP_OBSERVATION
        return
    with client.start_as_current_observation(name=name, as_type=as_type, **attributes) as current:
        yield current


@contextmanager
def request_trace(name: str, entrypoint: str, input: Any) -> Iterator[Any]:
    client = get_langfuse()
    if client is None:
        yield _NO_OP_OBSERVATION
        return
    # A tag do ponto de entrada (api/mcp/cli) e propagada a todas as observacoes do
    # trace, para filtrar na UI por origem do pedido.
    with propagate_attributes(trace_name=name, tags=[entrypoint]):
        with client.start_as_current_observation(name=name, as_type="agent", input=input) as root:
            yield root


def flush() -> None:
    client = get_langfuse()
    if client is not None:
        client.flush()
