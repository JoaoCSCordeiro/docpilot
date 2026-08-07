from functools import lru_cache

from fastapi import Depends, FastAPI

from src.agent.graph import build_default_graph
from src.api.schemas import QueryRequest, QueryResponse

app = FastAPI(
    title="DocPilot",
    description="Agente de perguntas-e-respostas sobre documentação técnica, com guardrail de confiança.",
)


@lru_cache(maxsize=1)
def get_graph():
    return build_default_graph()


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, graph=Depends(get_graph)) -> QueryResponse:
    result = graph.invoke({"query": request.question})
    return QueryResponse(
        answer=result["answer"],
        is_confident=result["is_confident"],
        confidence=result["confidence"],
    )
