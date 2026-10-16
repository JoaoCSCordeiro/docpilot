from qdrant_client import QdrantClient

from src.agent.guardrail import confidence_score
from src.evaluation.dataset import EvalCase
from src.evaluation.metrics import (
    mean,
    mean_by_group,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    refusal_metrics,
)
from src.retrieval.reranker import rerank
from src.retrieval.retriever import RetrievedChunk, retrieve

RETRIEVAL_CATEGORIES = ("in_scope",)
# Casos da coleccao principal com should_refuse anotado de forma fiavel; os indiretos
# vivem noutra coleccao e respondem sobre documentos que so existem nela.
REFUSAL_CATEGORIES = ("in_scope", "out_of_scope", "injection_direct")


def retrieval_row(
    case: EvalCase, retrieved: list[RetrievedChunk], reranked: list[RetrievedChunk]
) -> dict:
    retrieved_sources = [chunk.source for chunk in retrieved]
    reranked_sources = [chunk.source for chunk in reranked]
    row = {
        "id": case.id,
        "category": case.category,
        "language": case.language,
        "document_language": case.document_language,
        "should_refuse": case.should_refuse,
        "expected_sources": case.expected_sources,
        "retrieved_sources": retrieved_sources,
        "reranked_sources": reranked_sources,
        "confidence": confidence_score(reranked),
    }
    if case.expected_sources:
        expected = case.expected_sources
        row.update(
            {
                "recall_at_k": recall_at_k(retrieved_sources, expected),
                "precision_at_k": precision_at_k(retrieved_sources, expected),
                "reciprocal_rank": reciprocal_rank(retrieved_sources, expected),
                "reciprocal_rank_after_rerank": reciprocal_rank(reranked_sources, expected),
                "precision_at_1_before_rerank": precision_at_k(retrieved_sources[:1], expected),
                "precision_at_1_after_rerank": precision_at_k(reranked_sources[:1], expected),
            }
        )
    return row


def evaluate_retrieval(
    client: QdrantClient, collections: dict[str, str], cases: list[EvalCase], top_k: int
) -> list[dict]:
    rows = []
    for case in cases:
        retrieved = retrieve(client, collections[case.collection], case.question, top_k)
        rows.append(retrieval_row(case, retrieved, rerank(case.question, retrieved)))
    return rows


def summarize_retrieval(rows: list[dict]) -> dict:
    scored = [row for row in rows if row["category"] in RETRIEVAL_CATEGORIES]
    summary = {
        "n": len(scored),
        "recall_at_k": mean(row["recall_at_k"] for row in scored),
        "precision_at_k": mean(row["precision_at_k"] for row in scored),
        "mrr": mean(row["reciprocal_rank"] for row in scored),
        "mrr_after_rerank": mean(row["reciprocal_rank_after_rerank"] for row in scored),
        "precision_at_1_before_rerank": mean(row["precision_at_1_before_rerank"] for row in scored),
        "precision_at_1_after_rerank": mean(row["precision_at_1_after_rerank"] for row in scored),
        "by_question_language": {},
        "by_document_language": {},
        "by_language_pair": {},
    }
    for row in scored:
        row["language_pair"] = f"{row['language']}->{row['document_language']}"
    for group_name, group_key in (
        ("by_question_language", "language"),
        ("by_document_language", "document_language"),
        ("by_language_pair", "language_pair"),
    ):
        for metric in ("recall_at_k", "precision_at_k", "reciprocal_rank"):
            for group, stats in mean_by_group(scored, group_key, metric).items():
                summary[group_name].setdefault(group, {"n": stats["n"]})[metric] = stats["mean"]
    return summary


def gate_metrics(summary: dict) -> dict[str, float]:
    metrics = {
        name: summary[name]
        for name in (
            "recall_at_k",
            "precision_at_k",
            "mrr",
            "precision_at_1_after_rerank",
        )
    }
    for group_name in ("by_question_language", "by_document_language"):
        for group, stats in summary[group_name].items():
            metrics[f"{group_name}.{group}.recall_at_k"] = stats["recall_at_k"]
    return metrics


def threshold_sweep(rows: list[dict], thresholds: list[float]) -> list[dict]:
    candidates = [row for row in rows if row["category"] in REFUSAL_CATEGORIES]
    should_refuse = [row["should_refuse"] for row in candidates]
    sweep = []
    for threshold in thresholds:
        refused = [row["confidence"] < threshold for row in candidates]
        # Recusar uma pergunta respondivel cujo documento nem chegou ao top-k e menos
        # grave do que recusar uma que o retrieval acertou: separa-se as duas.
        answerable_with_hit_refused = sum(
            1
            for row, is_refused in zip(candidates, refused)
            if not row["should_refuse"] and row.get("recall_at_k", 0) > 0 and is_refused
        )
        sweep.append(
            {
                "threshold": threshold,
                **refusal_metrics(should_refuse, refused),
                "answerable_with_retrieval_hit_refused": answerable_with_hit_refused,
            }
        )
    return sweep
