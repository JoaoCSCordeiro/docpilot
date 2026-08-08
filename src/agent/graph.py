from typing import TypedDict

from langgraph.graph import END, StateGraph
from qdrant_client import QdrantClient

from src.agent.guardrail import confidence_score, is_confident
from src.agent.llm import get_llm
from src.config import settings
from src.retrieval.reranker import rerank
from src.retrieval.retriever import RetrievedChunk, retrieve
from src.retrieval.vector_store import get_client

REFUSAL_MESSAGE = (
    "Não tenho informação suficiente na documentação disponível para responder "
    "com confiança a essa pergunta."
)

_PROMPT_TEMPLATE = """Responde à pergunta usando apenas a informação no contexto abaixo. \
Não inventes informação que não esteja no contexto.

Contexto:
{context}

Pergunta: {query}"""


class AgentState(TypedDict):
    query: str
    retrieved_chunks: list[RetrievedChunk]
    reranked_chunks: list[RetrievedChunk]
    confidence: float
    is_confident: bool
    answer: str


def _build_context(chunks: list[RetrievedChunk]) -> str:
    return "\n\n".join(f"[{chunk.source}] {chunk.text}" for chunk in chunks)


def build_graph(
    client: QdrantClient, llm, collection_name: str | None = None, top_k: int | None = None
):
    effective_collection_name = collection_name or settings.qdrant_collection_name
    effective_top_k = top_k or settings.retrieval_top_k

    def retrieve_node(state: AgentState) -> dict:
        chunks = retrieve(client, effective_collection_name, state["query"], effective_top_k)
        return {"retrieved_chunks": chunks}

    def rerank_node(state: AgentState) -> dict:
        reranked = rerank(state["query"], state["retrieved_chunks"])
        return {"reranked_chunks": reranked}

    def assess_confidence_node(state: AgentState) -> dict:
        chunks = state["reranked_chunks"]
        return {
            "confidence": confidence_score(chunks),
            "is_confident": is_confident(chunks),
        }

    def route_by_confidence(state: AgentState) -> str:
        return "generate_answer" if state["is_confident"] else "refuse"

    def generate_answer_node(state: AgentState) -> dict:
        prompt = _PROMPT_TEMPLATE.format(
            context=_build_context(state["reranked_chunks"]), query=state["query"]
        )
        response = llm.invoke(prompt)
        return {"answer": response.content}

    def refuse_node(state: AgentState) -> dict:
        return {"answer": REFUSAL_MESSAGE}

    graph = StateGraph(AgentState)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("rerank", rerank_node)
    graph.add_node("assess_confidence", assess_confidence_node)
    graph.add_node("generate_answer", generate_answer_node)
    graph.add_node("refuse", refuse_node)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "rerank")
    graph.add_edge("rerank", "assess_confidence")
    graph.add_conditional_edges(
        "assess_confidence",
        route_by_confidence,
        {"generate_answer": "generate_answer", "refuse": "refuse"},
    )
    graph.add_edge("generate_answer", END)
    graph.add_edge("refuse", END)

    return graph.compile()


def build_default_graph():
    return build_graph(get_client(), get_llm())
