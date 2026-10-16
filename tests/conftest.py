import pytest

from src.observability import tracing


@pytest.fixture(autouse=True)
def disable_langfuse_tracing():
    # O .env local pode ter chaves Langfuse reais; os testes nunca exportam traces.
    tracing.set_langfuse_client(None)
    yield
    tracing.set_langfuse_client(None)
