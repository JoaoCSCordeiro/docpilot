import datetime as dt

import mongomock

from src.agent.query_log import get_low_confidence_queries, get_recent_queries, save_query_trace
from src.retrieval.retriever import RetrievedChunk


def _collection():
    client = mongomock.MongoClient()
    return client["test_db"]["query_traces"]


def _fake_state(**overrides):
    state = {
        "query": "pergunta",
        "retrieved_chunks": [RetrievedChunk(source="a.md", position=0, text="texto a", score=0.8)],
        "reranked_chunks": [RetrievedChunk(source="a.md", position=0, text="texto a", score=2.1)],
        "confidence": 0.9,
        "is_confident": True,
        "answer": "resposta",
    }
    state.update(overrides)
    return state


def test_save_query_trace_stores_expected_fields() -> None:
    collection = _collection()

    save_query_trace(collection, _fake_state())

    document = collection.find_one()
    assert document["question"] == "pergunta"
    assert document["confidence"] == 0.9
    assert document["is_confident"] is True
    assert document["answer"] == "resposta"
    assert document["retrieved_chunks"] == [{"source": "a.md", "position": 0, "score": 0.8}]
    assert document["reranked_chunks"] == [{"source": "a.md", "position": 0, "score": 2.1}]
    assert "created_at" in document


def test_get_recent_queries_returns_most_recent_first() -> None:
    collection = _collection()
    base_time = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    save_query_trace(collection, _fake_state(query="primeira"), created_at=base_time)
    save_query_trace(
        collection, _fake_state(query="segunda"), created_at=base_time + dt.timedelta(seconds=1)
    )

    recent = get_recent_queries(collection, limit=10)

    assert [doc["question"] for doc in recent] == ["segunda", "primeira"]


def test_get_recent_queries_respects_limit() -> None:
    collection = _collection()
    for i in range(5):
        save_query_trace(collection, _fake_state(query=f"pergunta {i}"))

    recent = get_recent_queries(collection, limit=2)

    assert len(recent) == 2


def test_get_low_confidence_queries_filters_by_threshold() -> None:
    collection = _collection()
    save_query_trace(collection, _fake_state(query="confiante", confidence=0.9))
    save_query_trace(collection, _fake_state(query="duvidosa", confidence=0.1))

    low_confidence = get_low_confidence_queries(collection, threshold=0.5)

    assert [doc["question"] for doc in low_confidence] == ["duvidosa"]
