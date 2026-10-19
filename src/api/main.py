from functools import lru_cache

from fastapi import Depends, FastAPI

from src.agent.graph import build_default_graph, run_agent
from src.agent.query_log import (
    get_mongo_client,
    get_query_traces_collection,
    try_save_query_trace,
)
from src.api.schemas import QueryRequest, QueryResponse, SourceChunk

app = FastAPI(
    title="DocPilot",
    description=(
        "Agente de perguntas-e-respostas sobre documentação técnica, com guardrail de confiança."
    ),
)


@lru_cache(maxsize=1)
def get_graph():
    return build_default_graph()


@lru_cache(maxsize=1)
def get_query_log_collection():
    return get_query_traces_collection(get_mongo_client())


# Liveness: so diz que o processo responde. Qdrant, MongoDB e Redis tem os seus proprios
# healthchecks no compose; se este endpoint os testasse, uma falha do Mongo reiniciava a API.
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query(
    request: QueryRequest,
    graph=Depends(get_graph),
    query_log=Depends(get_query_log_collection),
) -> QueryResponse:
    result = run_agent(graph, request.question, entrypoint="api")
    try_save_query_trace(query_log, result)
    return QueryResponse(
        answer=result["answer"],
        is_confident=result["is_confident"],
        confidence=result["confidence"],
        sources=[
            SourceChunk(source=chunk.source, position=chunk.position, score=chunk.score)
            for chunk in result.get("reranked_chunks", [])
        ],
    )
