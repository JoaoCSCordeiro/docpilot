from functools import lru_cache

from fastapi import Depends, FastAPI

from src.agent.graph import build_default_graph
from src.agent.query_log import get_mongo_client, get_query_traces_collection, save_query_trace
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


@app.post("/query", response_model=QueryResponse)
def query(
    request: QueryRequest,
    graph=Depends(get_graph),
    query_log=Depends(get_query_log_collection),
) -> QueryResponse:
    result = graph.invoke({"query": request.question})
    save_query_trace(query_log, result)
    return QueryResponse(
        answer=result["answer"],
        is_confident=result["is_confident"],
        confidence=result["confidence"],
        sources=[
            SourceChunk(source=chunk.source, position=chunk.position, score=chunk.score)
            for chunk in result.get("reranked_chunks", [])
        ],
    )
