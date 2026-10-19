import mongomock
import pytest
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from src.api.main import app, get_graph, get_query_log_collection
from src.config import settings
from src.retrieval.retriever import RetrievedChunk


class FakeGraph:
    def __init__(self, result: dict) -> None:
        self._result = result

    def invoke(self, state: dict) -> dict:
        return self._result


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[get_query_log_collection] = lambda: mongomock.MongoClient()["test_db"][
        "query_traces"
    ]
    return TestClient(app)


class FailingCollection:
    def insert_one(self, document: dict) -> None:
        raise ServerSelectionTimeoutError("mongo down")


def _override_graph(result: dict) -> None:
    app.dependency_overrides[get_graph] = lambda: FakeGraph(result)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_query_endpoint_returns_confident_answer(client: TestClient) -> None:
    _override_graph(
        {
            "query": "O que e o FastAPI?",
            "answer": "FastAPI e uma framework web para Python.",
            "is_confident": True,
            "confidence": 0.83,
        }
    )

    response = client.post("/query", json={"question": "O que e o FastAPI?"})

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "FastAPI e uma framework web para Python."
    assert data["is_confident"] is True
    assert data["confidence"] == pytest.approx(0.83)


def test_query_endpoint_returns_refusal(client: TestClient) -> None:
    _override_graph(
        {
            "query": "Qual e a capital da Mongolia?",
            "answer": "Não tenho informação suficiente para responder com confiança.",
            "is_confident": False,
            "confidence": 0.02,
        }
    )

    response = client.post("/query", json={"question": "Qual e a capital da Mongolia?"})

    assert response.status_code == 200
    data = response.json()
    assert data["is_confident"] is False


def test_query_endpoint_returns_sources_of_reranked_chunks(client: TestClient) -> None:
    _override_graph(
        {
            "query": "O que e o FastAPI?",
            "answer": "FastAPI e uma framework web para Python.",
            "is_confident": True,
            "confidence": 0.83,
            "reranked_chunks": [
                RetrievedChunk(source="fastapi.md", position=3, text="...", score=1.6)
            ],
        }
    )

    response = client.post("/query", json={"question": "O que e o FastAPI?"})

    assert response.json()["sources"] == [{"source": "fastapi.md", "position": 3, "score": 1.6}]


def test_query_endpoint_still_answers_when_the_query_log_is_down() -> None:
    _override_graph(
        {
            "query": "O que e o FastAPI?",
            "answer": "FastAPI e uma framework web para Python.",
            "is_confident": True,
            "confidence": 0.83,
        }
    )
    app.dependency_overrides[get_query_log_collection] = lambda: FailingCollection()

    response = TestClient(app).post("/query", json={"question": "O que e o FastAPI?"})

    assert response.status_code == 200
    assert response.json()["answer"] == "FastAPI e uma framework web para Python."


def test_query_endpoint_rejects_empty_question(client: TestClient) -> None:
    _override_graph({"answer": "", "is_confident": False, "confidence": 0.0})

    response = client.post("/query", json={"question": ""})

    assert response.status_code == 422


def test_query_endpoint_rejects_question_longer_than_the_limit(client: TestClient) -> None:
    _override_graph({"answer": "", "is_confident": False, "confidence": 0.0})

    response = client.post("/query", json={"question": "a" * (settings.max_question_length + 1)})

    assert response.status_code == 422


def test_health_endpoint_does_not_depend_on_the_graph(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_docs_endpoint_is_available(client: TestClient) -> None:
    response = client.get("/docs")

    assert response.status_code == 200
