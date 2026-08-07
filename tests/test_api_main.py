import mongomock
import pytest
from fastapi.testclient import TestClient

from src.api.main import app, get_graph, get_query_log_collection


class FakeGraph:
    def __init__(self, result: dict) -> None:
        self._result = result

    def invoke(self, state: dict) -> dict:
        return self._result


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[get_query_log_collection] = (
        lambda: mongomock.MongoClient()["test_db"]["query_traces"]
    )
    return TestClient(app)


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


def test_query_endpoint_rejects_empty_question(client: TestClient) -> None:
    _override_graph({"answer": "", "is_confident": False, "confidence": 0.0})

    response = client.post("/query", json={"question": ""})

    assert response.status_code == 422


def test_docs_endpoint_is_available(client: TestClient) -> None:
    response = client.get("/docs")

    assert response.status_code == 200
