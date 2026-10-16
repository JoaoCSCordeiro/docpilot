import argparse
import datetime as dt
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.graph import (  # noqa: E402
    GENERATION_PROMPT_VERSION,
    build_generation_prompt,
    build_graph,
    run_agent,
)
from src.agent.llm import get_llm  # noqa: E402
from src.agent.llm_cache import get_cached_response  # noqa: E402
from src.config import settings  # noqa: E402
from src.evaluation.checks import citation_check, is_abstention, leaked_strings  # noqa: E402
from src.evaluation.dataset import (  # noqa: E402
    DATASET_V2_PATH,
    POISONED_DIR,
    POISONED_SOURCE_PREFIX,
    EvalCase,
    load_cases,
)
from src.evaluation.judge import (  # noqa: E402
    JUDGE_PROMPT_VERSION,
    LABEL_SCORES,
    JudgeError,
    get_judge_llm,
    judge_answer,
)
from src.evaluation.metrics import mean, refusal_metrics  # noqa: E402
from src.evaluation.retrieval_eval import (  # noqa: E402
    REFUSAL_CATEGORIES,
    retrieval_row,
    summarize_retrieval,
    threshold_sweep,
)
from src.ingestion.indexing import index_documents  # noqa: E402
from src.ingestion.loader import Document, load_documents  # noqa: E402
from src.observability.tracing import flush, request_trace, score_trace  # noqa: E402
from src.retrieval.reranker import rerank  # noqa: E402
from src.retrieval.retriever import retrieve  # noqa: E402
from src.retrieval.vector_store import get_client  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
OUTPUT_DIR = REPO_ROOT / "docs" / "evaluation"
INJECTION_COLLECTION_SUFFIX = "_eval_injection"
SWEEP_THRESHOLDS = [round(0.05 * step, 2) for step in range(1, 20)]


def git_commit() -> str:
    def run(*command: str) -> str:
        return subprocess.run(command, capture_output=True, text=True, cwd=REPO_ROOT).stdout

    commit = run("git", "rev-parse", "--short", "HEAD").strip() or "unknown"
    dirty = bool(run("git", "status", "--porcelain", "--", "src", "scripts", "data").strip())
    return f"{commit}{' (working tree with uncommitted changes)' if dirty else ''}"


def build_injection_collection(client, collection_name: str) -> int:
    poisoned = [
        Document(source=POISONED_SOURCE_PREFIX + document.source, content=document.content)
        for document in load_documents(POISONED_DIR)
    ]
    # Recriada a cada execucao a partir do corpus principal mais os envenenados, para a
    # coleccao principal nunca ver os documentos com injection.
    return index_documents(
        client, collection_name, load_documents(RAW_DIR) + poisoned, recreate=True
    )


def estimate_groq_calls(
    cases: list[EvalCase], retrieval_rows: list[dict], reranked: dict[int, list]
) -> dict:
    confident = [
        case
        for case, row in zip(cases, retrieval_rows)
        if row["confidence"] >= settings.confidence_threshold
    ]
    uncached = [
        case
        for case in confident
        if get_cached_response(
            settings.groq_model, build_generation_prompt(case.question, reranked[case.id])
        )
        is None
    ]
    return {
        "cases": len(cases),
        "pass_guardrail": len(confident),
        "generation_calls_uncached": len(uncached),
        # Limite superior: o juiz so corre sobre respostas que nao sao abstencao, e as
        # que ja estiverem em cache nao custam chamadas.
        "judge_calls_upper_bound": len(confident),
    }


def evaluate_case(case: EvalCase, state: dict, retrieval_row: dict) -> dict:
    refused_by_guardrail = not state["is_confident"]
    answer = state["answer"]
    reranked = state.get("reranked_chunks", [])
    record = {
        "id": case.id,
        "question": case.question,
        "category": case.category,
        "language": case.language,
        "document_language": case.document_language,
        "collection": case.collection,
        "should_refuse": case.should_refuse,
        "expected_sources": case.expected_sources,
        "expected_answer_hint": case.expected_answer_hint,
        "confidence": state["confidence"],
        "refused_by_guardrail": refused_by_guardrail,
        "answer": answer,
        "abstained": not refused_by_guardrail and is_abstention(answer),
        "context": [
            {**chunk.summary(), "text": chunk.text}
            for chunk in (reranked if not refused_by_guardrail else [])
        ],
        "retrieval": {
            key: value
            for key, value in retrieval_row.items()
            if key.endswith(("_at_k", "rank", "_rerank", "_sources"))
        },
        "trace_id": state.get("trace_id"),
    }
    record["refused_end_to_end"] = refused_by_guardrail or record["abstained"]
    if not refused_by_guardrail and not record["abstained"]:
        record["citations"] = citation_check(answer, [chunk.source for chunk in reranked])
    if case.forbidden_strings:
        record["leaked_strings"] = leaked_strings(answer, case.forbidden_strings)
        context_text = " ".join(chunk.text for chunk in reranked)
        record["injection_in_context"] = bool(leaked_strings(context_text, case.forbidden_strings))
    return record


def run_judge(records: list[dict], cases_by_id: dict[int, EvalCase], states: dict) -> int:
    judge_llm = get_judge_llm()
    for record in records:
        if record["refused_end_to_end"]:
            continue
        state = states[record["id"]]
        with request_trace("docpilot-judge", "eval", input={"case_id": record["id"]}) as trace:
            try:
                verdict = judge_answer(
                    judge_llm,
                    cases_by_id[record["id"]].question,
                    record["answer"],
                    state["reranked_chunks"],
                )
            except JudgeError as error:
                record["judge"] = {"error": str(error)}
                continue
            trace.update(output=verdict.model_dump())
        record["judge"] = verdict.model_dump()
        for criterion in ("faithfulness", "relevance"):
            label = getattr(verdict, criterion)
            score_trace(
                record["trace_id"],
                f"judge_{criterion}",
                LABEL_SCORES[label],
                comment=f"{label} (judge {settings.judge_model}, rubric {JUDGE_PROMPT_VERSION})",
            )
    return judge_llm.groq_call_count


def summarize(records: list[dict]) -> dict:
    refusal_records = [r for r in records if r["category"] in REFUSAL_CATEGORIES]
    should_refuse = [r["should_refuse"] for r in refusal_records]
    answered = [r for r in records if not r["refused_end_to_end"]]
    cited = [r for r in answered if "citations" in r]
    judged = [r for r in answered if "judge" in r and "error" not in r["judge"]]
    injection = [r for r in records if r["category"].startswith("injection")]

    def label_counts(criterion: str) -> dict:
        return dict(Counter(r["judge"][criterion] for r in judged))

    return {
        "decisions_by_category": {
            category: {
                "n": len(group),
                "refused_by_guardrail": sum(r["refused_by_guardrail"] for r in group),
                "abstained": sum(r["abstained"] for r in group),
                "answered": sum(not r["refused_end_to_end"] for r in group),
            }
            for category in sorted({r["category"] for r in records})
            for group in [[r for r in records if r["category"] == category]]
        },
        "refusal_guardrail_only": refusal_metrics(
            should_refuse, [r["refused_by_guardrail"] for r in refusal_records]
        ),
        "refusal_end_to_end": refusal_metrics(
            should_refuse, [r["refused_end_to_end"] for r in refusal_records]
        ),
        "citations": {
            "n": len(cited),
            "with_citation": sum(r["citations"]["has_citation"] for r in cited),
            "in_requested_format": sum(r["citations"]["uses_requested_format"] for r in cited),
            "all_citations_in_context": sum(
                r["citations"]["all_citations_in_context"] for r in cited
            ),
        },
        "injection": {
            "n": len(injection),
            "with_forbidden_string_leaked": sum(bool(r.get("leaked_strings")) for r in injection),
            "indirect_with_injection_in_context": sum(
                r.get("injection_in_context", False)
                for r in injection
                if r["category"] == "injection_indirect"
            ),
        },
        "judge": {
            "n": len(judged),
            "errors": sum(1 for r in answered if "error" in r.get("judge", {})),
            "faithfulness_mean": mean(LABEL_SCORES[r["judge"]["faithfulness"]] for r in judged),
            "relevance_mean": mean(LABEL_SCORES[r["judge"]["relevance"]] for r in judged),
            "faithfulness_labels": label_counts("faithfulness"),
            "relevance_labels": label_counts("relevance"),
        },
    }


def fmt(value) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}" if isinstance(value, float) else str(value)


def render_report(results: dict) -> str:
    run = results["run"]
    retrieval = results["retrieval"]
    summary = results["summary"]
    lines = [
        "# LLM evaluation report",
        "",
        f"- Date: {run['date']}",
        f"- Commit: {run['commit']}",
        f"- Command: `{run['command']}`",
        f"- Dataset: `{run['dataset']}`, N = {run['n_cases']} cases",
        f"- Generator: `{run['generator_model']}` (prompt {run['generation_prompt_version']}), "
        f"guardrail threshold {run['confidence_threshold']}, top_k {run['top_k']}",
        f"- Judge: `{run['judge_model']}` (rubric {run['judge_prompt_version']}, "
        f"temperature 0, reasoning_effort={run['judge_reasoning_effort'] or 'model default'})",
        f"- Embeddings: `{run['embedding_model']}`, reranker: `{run['reranker_model']}`",
        f"- Groq calls made in this run: generation {run['groq_calls']['generation']}, "
        f"judge {run['groq_calls']['judge']} (the rest came from the local cache)",
        "",
        f"## Retrieval (in_scope cases, N = {retrieval['n']})",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    for name in (
        "recall_at_k",
        "precision_at_k",
        "mrr",
        "mrr_after_rerank",
        "precision_at_1_before_rerank",
        "precision_at_1_after_rerank",
    ):
        lines.append(f"| {name} | {fmt(retrieval[name])} |")
    lines += ["", "| Question -> document language | N | Recall@k | Precision@k | MRR |"]
    lines.append("|---|---|---|---|---|")
    for pair, stats in retrieval["by_language_pair"].items():
        lines.append(
            f"| {pair} | {stats['n']} | {fmt(stats['recall_at_k'])} | "
            f"{fmt(stats['precision_at_k'])} | {fmt(stats['reciprocal_rank'])} |"
        )

    lines += [
        "",
        "## Decisions by category",
        "",
        "| Category | N | Guardrail refused | LLM abstained | Answered |",
        "|---|---|---|---|---|",
    ]
    for category, stats in summary["decisions_by_category"].items():
        lines.append(
            f"| {category} | {stats['n']} | {stats['refused_by_guardrail']} | "
            f"{stats['abstained']} | {stats['answered']} |"
        )

    lines += [
        "",
        "## Refusal (in_scope + out_of_scope + injection_direct)",
        "",
        "| Refusal counted as | N | Precision | Recall | TP | FP | FN |",
        "|---|---|---|---|---|---|---|",
    ]
    for label, key in (
        ("guardrail only", "refusal_guardrail_only"),
        ("guardrail or LLM abstention", "refusal_end_to_end"),
    ):
        stats = summary[key]
        lines.append(
            f"| {label} | {stats['n']} | {fmt(stats['precision'])} | {fmt(stats['recall'])} | "
            f"{stats['true_refusals']} | {stats['false_refusals']} | {stats['missed_refusals']} |"
        )

    citations = summary["citations"]
    injection = summary["injection"]
    lines += [
        "",
        "## Deterministic checks",
        "",
        f"- Answers with at least one source citation: {citations['with_citation']}"
        f"/{citations['n']}",
        f"- Answers using the requested `[file.md]` format (the rest used gpt-oss's native "
        f"`【file.md】`): {citations['in_requested_format']}/{citations['n']}",
        f"- Answers whose citations all exist in the retrieved context: "
        f"{citations['all_citations_in_context']}/{citations['n']}",
        f"- Prompt injection cases with a forbidden string (canary or injected text) in the "
        f"answer: {injection['with_forbidden_string_leaked']}/{injection['n']}",
        f"- Indirect injection cases where the poisoned passage reached the LLM context: "
        f"{injection['indirect_with_injection_in_context']}/"
        f"{summary['decisions_by_category'].get('injection_indirect', {}).get('n', 0)}",
    ]

    judge = summary["judge"]
    lines += [
        "",
        f"## LLM-as-a-judge on {judge['n']} answered questions",
        "",
        f"- Faithfulness mean (supported=1, partially=0.5, unsupported=0): "
        f"{fmt(judge['faithfulness_mean'])}, labels {judge['faithfulness_labels']}",
        f"- Answer relevance mean (relevant=1, partially=0.5, irrelevant=0): "
        f"{fmt(judge['relevance_mean'])}, labels {judge['relevance_labels']}",
        f"- Judge outputs rejected by schema validation: {judge['errors']}",
    ]

    lines += [
        "",
        "## Guardrail threshold sweep (retrieval only, no LLM)",
        "",
        "| Threshold | Refusal precision | Refusal recall | Correct refusals | "
        "Wrong refusals | Missed refusals | Wrong refusals with retrieval hit |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in results["threshold_sweep"]:
        lines.append(
            f"| {row['threshold']:.2f} | {fmt(row['precision'])} | {fmt(row['recall'])} | "
            f"{row['true_refusals']} | {row['false_refusals']} | {row['missed_refusals']} | "
            f"{row['answerable_with_retrieval_hit_refused']} |"
        )

    lines += [
        "",
        "## Per case",
        "",
        "| ID | Category | Lang | Confidence | Outcome | Citations ok | Leak | "
        "Faithfulness | Relevance |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for record in results["cases"]:
        outcome = (
            "refused"
            if record["refused_by_guardrail"]
            else ("abstained" if record["abstained"] else "answered")
        )
        citations_ok = record.get("citations", {}).get("all_citations_in_context")
        judge_verdict = record.get("judge", {})
        lines.append(
            f"| {record['id']} | {record['category']} | {record['language']} | "
            f"{record['confidence']:.3f} | {outcome} | "
            f"{'' if citations_ok is None else ('yes' if citations_ok else 'no')} | "
            f"{', '.join(record.get('leaked_strings', []))} | "
            f"{judge_verdict.get('faithfulness', '')} | {judge_verdict.get('relevance', '')} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="DocPilot LLM evaluation (dataset v2)")
    parser.add_argument(
        "--dry-run", action="store_true", help="So retrieval e estimativa de chamadas a Groq."
    )
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument("--ids", type=int, nargs="*", help="Corre so estes casos.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    cases = load_cases()
    if args.ids:
        cases = [case for case in cases if case.id in set(args.ids)]
    cases_by_id = {case.id: case for case in cases}

    client = get_client()
    collections = {
        "main": settings.qdrant_collection_name,
        "injection": settings.qdrant_collection_name + INJECTION_COLLECTION_SUFFIX,
    }
    chunk_count = build_injection_collection(client, collections["injection"])
    print(f"Coleccao de avaliacao '{collections['injection']}': {chunk_count} chunks")

    # Passo sem LLM: da as metricas de retrieval, o sweep do threshold e os prompts
    # exatos que o gerador vai receber (para a estimativa de chamadas).
    retrieval_rows = []
    reranked_by_id = {}
    for case in cases:
        retrieved = retrieve(
            client, collections[case.collection], case.question, settings.retrieval_top_k
        )
        reranked_by_id[case.id] = rerank(case.question, retrieved)
        retrieval_rows.append(retrieval_row(case, retrieved, reranked_by_id[case.id]))
    retrieval_by_id = {row["id"]: row for row in retrieval_rows}

    estimate = estimate_groq_calls(cases, retrieval_rows, reranked_by_id)
    print(json.dumps(estimate, indent=2))
    if args.dry_run:
        return

    llm = get_llm()
    graphs = {
        name: build_graph(client, llm, collection_name=collection)
        for name, collection in collections.items()
    }
    states = {}
    records = []
    for case in cases:
        state = run_agent(graphs[case.collection], case.question, entrypoint="eval")
        states[case.id] = state
        records.append(evaluate_case(case, state, retrieval_by_id[case.id]))
        print(
            f"[{case.id}] {'refused' if not state['is_confident'] else 'answered'} "
            f"conf={state['confidence']:.3f}"
        )

    judge_calls = 0 if args.skip_judge else run_judge(records, cases_by_id, states)
    flush()

    results = {
        "run": {
            "date": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "commit": git_commit(),
            "command": "python -X utf8 scripts/run_llm_evaluation.py " + " ".join(sys.argv[1:]),
            "dataset": DATASET_V2_PATH.relative_to(REPO_ROOT).as_posix(),
            "n_cases": len(cases),
            "generator_model": settings.groq_model,
            "generation_prompt_version": GENERATION_PROMPT_VERSION,
            "judge_model": None if args.skip_judge else settings.judge_model,
            "judge_prompt_version": JUDGE_PROMPT_VERSION,
            "judge_reasoning_effort": settings.judge_reasoning_effort,
            "confidence_threshold": settings.confidence_threshold,
            "top_k": settings.retrieval_top_k,
            "embedding_model": settings.embedding_model_name,
            "reranker_model": settings.reranker_model_name,
            "groq_calls": {"generation": llm.groq_call_count, "judge": judge_calls},
        },
        "retrieval": summarize_retrieval(retrieval_rows),
        "summary": summarize(records),
        "threshold_sweep": threshold_sweep(retrieval_rows, SWEEP_THRESHOLDS),
        "cases": records,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "llm-eval-results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "llm-eval-report.md").write_text(render_report(results), encoding="utf-8")
    print(
        json.dumps(
            {"run": results["run"], "summary": results["summary"]}, indent=2, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
