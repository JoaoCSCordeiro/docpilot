from typing import TypedDict

from langgraph.graph import END, StateGraph
from qdrant_client import QdrantClient

from src.agent.guardrail import confidence_score, is_confident
from src.agent.llm import get_llm
from src.config import settings
from src.observability.tracing import observation, request_trace
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
        with observation(
            "retrieve",
            as_type="retriever",
            input={"query": state["query"], "top_k": effective_top_k},
            metadata={
                "collection": effective_collection_name,
                "embedding_model": settings.embedding_model_name,
            },
        ) as span:
            chunks = retrieve(client, effective_collection_name, state["query"], effective_top_k)
            span.update(output=[chunk.summary() for chunk in chunks])
        return {"retrieved_chunks": chunks}

    def rerank_node(state: AgentState) -> dict:
        with observation(
            "rerank",
            input=[chunk.summary() for chunk in state["retrieved_chunks"]],
            metadata={"reranker_model": settings.reranker_model_name},
        ) as span:
            reranked = rerank(state["query"], state["retrieved_chunks"])
            span.update(output=[chunk.summary() for chunk in reranked])
        return {"reranked_chunks": reranked}

    def assess_confidence_node(state: AgentState) -> dict:
        chunks = state["reranked_chunks"]
        with observation("assess_confidence", as_type="guardrail") as span:
            result = {
                "confidence": confidence_score(chunks),
                "is_confident": is_confident(chunks),
            }
            span.update(output={**result, "threshold": settings.confidence_threshold})
        return result

    def route_by_confidence(state: AgentState) -> str:
        return "generate_answer" if state["is_confident"] else "refuse"

    def generate_answer_node(state: AgentState) -> dict:
        prompt = _PROMPT_TEMPLATE.format(
            context=_build_context(state["reranked_chunks"]), query=state["query"]
        )
        with observation("generate_answer", as_type="chain") as span:
            response = llm.invoke(prompt)
            span.update(output=response.content)
        return {"answer": response.content}

    def refuse_node(state: AgentState) -> dict:
        with observation("refuse", output=REFUSAL_MESSAGE):
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


def run_agent(graph, question: str, entrypoint: str) -> AgentState:
    with request_trace("docpilot-query", entrypoint, input={"question": question}) as trace:
        state = graph.invoke({"query": question})
        trace.update(
            output={
                "answer": state["answer"],
                "decision": "answered" if state["is_confident"] else "refused",
                "confidence": state["confidence"],
            }
        )
    return state
