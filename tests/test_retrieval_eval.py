import pytest

from src.evaluation.dataset import EvalCase
from src.evaluation.gate import find_regressions
from src.evaluation.retrieval_eval import (
    gate_metrics,
    retrieval_row,
    summarize_retrieval,
    threshold_sweep,
)
from src.retrieval.retriever import RetrievedChunk


def make_case(case_id: int, language: str, sources: list[str], **overrides) -> EvalCase:
    fields = {
        "id": case_id,
        "question": f"pergunta {case_id}",
        "language": language,
        "category": "in_scope",
        "should_refuse": False,
        "expected_sources": sources,
        "expected_answer_hint": "",
        "document_language": "en" if sources else None,
    }
    fields.update(overrides)
    return EvalCase(**fields)


def chunks(*sources_and_scores: tuple[str, float]) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(source=source, position=0, text="", score=score)
        for source, score in sources_and_scores
    ]


def test_retrieval_row_scores_before_and_after_rerank() -> None:
    case = make_case(1, "pt", ["a.md"])
    retrieved = chunks(("b.md", 0.9), ("a.md", 0.8))
    reranked = chunks(("a.md", 3.0), ("b.md", -2.0))

    row = retrieval_row(case, retrieved, reranked)

    assert row["recall_at_k"] == 1.0
    assert row["reciprocal_rank"] == 0.5
    assert row["reciprocal_rank_after_rerank"] == 1.0
    assert row["precision_at_1_before_rerank"] == 0.0
    assert row["precision_at_1_after_rerank"] == 1.0
    assert row["confidence"] == pytest.approx(0.9526, abs=1e-4)


def test_out_of_scope_rows_have_confidence_but_no_retrieval_scores() -> None:
    case = make_case(2, "en", [], category="out_of_scope", should_refuse=True)

    row = retrieval_row(case, chunks(("a.md", 0.1)), chunks(("a.md", -5.0)))

    assert "recall_at_k" not in row
    assert row["confidence"] < 0.01


def test_summary_uses_only_in_scope_rows_and_splits_by_language() -> None:
    rows = [
        retrieval_row(make_case(1, "pt", ["a.md"]), chunks(("a.md", 1.0)), chunks(("a.md", 1.0))),
        retrieval_row(make_case(2, "en", ["a.md"]), chunks(("b.md", 1.0)), chunks(("b.md", 1.0))),
        retrieval_row(
            make_case(3, "en", [], category="out_of_scope", should_refuse=True),
            chunks(("b.md", 1.0)),
            chunks(("b.md", -9.0)),
        ),
    ]

    summary = summarize_retrieval(rows)

    assert summary["n"] == 2
    assert summary["recall_at_k"] == 0.5
    assert summary["by_question_language"]["pt"]["recall_at_k"] == 1.0
    assert summary["by_question_language"]["en"]["recall_at_k"] == 0.0
    assert summary["by_language_pair"]["en->en"]["n"] == 1
    assert "by_question_language.en.recall_at_k" in gate_metrics(summary)


def test_threshold_sweep_trades_wrong_refusals_for_missed_refusals() -> None:
    answerable = retrieval_row(
        make_case(1, "pt", ["a.md"]), chunks(("a.md", 1.0)), chunks(("a.md", 0.0))
    )
    out_of_scope = retrieval_row(
        make_case(2, "pt", [], category="out_of_scope", should_refuse=True),
        chunks(("a.md", 1.0)),
        chunks(("a.md", -1.0)),
    )

    low, high = threshold_sweep([answerable, out_of_scope], [0.3, 0.6])

    assert (low["true_refusals"], low["false_refusals"]) == (1, 0)
    assert (high["true_refusals"], high["false_refusals"]) == (1, 1)
    assert high["answerable_with_retrieval_hit_refused"] == 1


def test_gate_passes_within_tolerance_and_fails_below_it() -> None:
    baseline = {"tolerance": 0.03, "metrics": {"recall_at_k": 0.6, "mrr": 0.5}}

    assert find_regressions({"recall_at_k": 0.58, "mrr": 0.5}, baseline) == []
    regressions = find_regressions({"recall_at_k": 0.55, "mrr": 0.5}, baseline)
    assert len(regressions) == 1 and regressions[0].startswith("recall_at_k")


def test_gate_fails_when_a_baseline_metric_is_missing() -> None:
    baseline = {"tolerance": 0.03, "metrics": {"mrr": 0.5}}

    assert find_regressions({}, baseline) == ["mrr: metrica em falta (baseline 0.5000)"]
