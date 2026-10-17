import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402
from src.evaluation.dataset import DATASET_V2_PATH, load_cases  # noqa: E402
from src.evaluation.metrics import mean  # noqa: E402
from src.evaluation.retrieval_eval import (  # noqa: E402
    REFUSAL_CATEGORIES,
    retrieval_row,
    summarize_retrieval,
    threshold_sweep,
)
from src.ingestion.indexing import index_documents  # noqa: E402
from src.ingestion.loader import load_documents  # noqa: E402
from src.retrieval.reranker import rerank  # noqa: E402
from src.retrieval.retriever import HYBRID_PREFETCH_LIMIT, RetrievalConfig, retrieve  # noqa: E402
from src.retrieval.vector_store import get_client  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
OUTPUT_PATH = REPO_ROOT / "docs" / "evaluation" / "retrieval-ablation.json"
ABLATION_COLLECTION = "docpilot_ablation"

DEFAULT_EMBEDDING_MODELS = [
    "sentence-transformers/all-MiniLM-L6-v2",
    "intfloat/multilingual-e5-small",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
]
DEFAULT_RERANKERS = [
    "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
]
# Mais fino perto de zero: no Bloco 18 o melhor ponto ficou no limite inferior da grelha.
# Threshold de producao ate ao Bloco 18, mantido como referencia de comparacao.
REFERENCE_THRESHOLD = 0.5
SWEEP_THRESHOLDS = [0.005, 0.01, 0.02, 0.03] + [round(0.05 * step, 2) for step in range(1, 20)]


def timed(function, *args, **kwargs):
    start = time.perf_counter()
    result = function(*args, **kwargs)
    return result, (time.perf_counter() - start) * 1000


def lowest_safe_threshold(sweep: list[dict], min_true_refusals: int) -> dict | None:
    # Nenhum limiar recusa as 10 perguntas a recusar (duas injections diretas falam de
    # termos do corpus). O criterio e nao recusar menos do que hoje e, entre esses limiares,
    # o mais baixo, que e o que menos recusa perguntas respondiveis.
    safe = [point for point in sweep if point["true_refusals"] >= min_true_refusals]
    return safe[0] if safe else None


def run_configuration(
    client, cases, top_k, config: RetrievalConfig, rerankers: list[str], min_true_refusals: int
):
    retrieve(client, ABLATION_COLLECTION, cases[0].question, top_k, config)
    retrieved_per_case = []
    retrieve_latencies = []
    for case in cases:
        retrieved, latency = timed(
            retrieve, client, ABLATION_COLLECTION, case.question, top_k, config
        )
        retrieved_per_case.append(retrieved)
        retrieve_latencies.append(latency)

    results = []
    for reranker in rerankers:
        rerank(cases[0].question, retrieved_per_case[0], reranker)
        rows = []
        rerank_latencies = []
        for case, retrieved in zip(cases, retrieved_per_case):
            reranked, latency = timed(rerank, case.question, retrieved, reranker)
            rerank_latencies.append(latency)
            rows.append(retrieval_row(case, retrieved, reranked))
        sweep = threshold_sweep(rows, SWEEP_THRESHOLDS)
        results.append(
            {
                "embedding_model": config.embedding_model if config.mode != "sparse" else None,
                "mode": config.mode,
                "bm25_language": config.bm25_language if config.mode != "dense" else None,
                "reranker": reranker,
                "retrieval": summarize_retrieval(rows),
                "latency_ms": {
                    "retrieve_mean": mean(retrieve_latencies),
                    "rerank_mean": mean(rerank_latencies),
                },
                "refusals_at_reference_threshold": threshold_sweep(rows, [REFERENCE_THRESHOLD])[0],
                "lowest_safe_threshold": lowest_safe_threshold(sweep, min_true_refusals),
                "threshold_sweep": sweep,
                "rows": rows,
            }
        )
    return results


def format_table(results: list[dict]) -> str:
    def short(name: str | None) -> str:
        return name.split("/")[-1] if name else "-"

    lines = [
        "| Embedding | Mode | BM25 | Reranker | R@5 | P@5 | MRR | MRR rr | P@1 rr "
        "| R@5 pt->en | R@5 en->pt | ms retr | ms rr "
        f"| wrong/right ref @{REFERENCE_THRESHOLD} | t* | wrong ref @t* |",
        "|" + "---|" * 16,
    ]
    for result in results:
        summary = result["retrieval"]
        pairs = summary["by_language_pair"]
        current = result["refusals_at_reference_threshold"]
        best = result["lowest_safe_threshold"]
        lines.append(
            f"| {short(result['embedding_model'])} | {result['mode']} "
            f"| {result['bm25_language'] or '-'} | {short(result['reranker'])} "
            f"| {summary['recall_at_k']:.4f} | {summary['precision_at_k']:.4f} "
            f"| {summary['mrr']:.4f} | {summary['mrr_after_rerank']:.4f} "
            f"| {summary['precision_at_1_after_rerank']:.4f} "
            f"| {pairs['pt->en']['recall_at_k']:.4f} | {pairs['en->pt']['recall_at_k']:.4f} "
            f"| {result['latency_ms']['retrieve_mean']:.1f} "
            f"| {result['latency_ms']['rerank_mean']:.1f} "
            f"| {current['false_refusals']}/{current['true_refusals']} "
            f"| {best['threshold'] if best else '-'} "
            f"| {best['false_refusals'] if best else '-'} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ablation de retrieval (sem LLM)")
    parser.add_argument("--embedding-models", nargs="+", default=DEFAULT_EMBEDDING_MODELS)
    parser.add_argument("--modes", nargs="+", default=["dense", "sparse", "hybrid"])
    parser.add_argument("--bm25-languages", nargs="+", default=[settings.bm25_language])
    parser.add_argument("--rerankers", nargs="+", default=DEFAULT_RERANKERS)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    # 8 = recusas certas da configuracao de producao do Bloco 18 com threshold 0.5.
    parser.add_argument("--min-true-refusals", type=int, default=8)
    args = parser.parse_args()

    cases = [
        case
        for case in load_cases()
        if case.collection == "main" and case.category in REFUSAL_CATEGORIES
    ]
    documents = load_documents(RAW_DIR)
    client = get_client()
    top_k = settings.retrieval_top_k

    results = []
    sparse_languages_done: set[str] = set()
    for embedding_model in args.embedding_models:
        for bm25_language in args.bm25_languages:
            chunk_count = index_documents(
                client,
                ABLATION_COLLECTION,
                documents,
                recreate=True,
                embedding_model=embedding_model,
                bm25_language=bm25_language,
            )
            print(f"Indexado: {embedding_model}, BM25 {bm25_language}, {chunk_count} chunks")
            for mode in args.modes:
                # O sparse nao depende do embedding: mede-se uma vez por lingua do BM25.
                if mode == "sparse" and bm25_language in sparse_languages_done:
                    continue
                if mode == "dense" and bm25_language != args.bm25_languages[0]:
                    continue
                config = RetrievalConfig(mode, embedding_model, bm25_language)
                results.extend(
                    run_configuration(
                        client, cases, top_k, config, args.rerankers, args.min_true_refusals
                    )
                )
                if mode == "sparse":
                    sparse_languages_done.add(bm25_language)
    client.delete_collection(ABLATION_COLLECTION)

    in_scope = sum(1 for case in cases if case.category == "in_scope")
    report = {
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "dataset": DATASET_V2_PATH.name,
        "n_cases": len(cases),
        "n_in_scope": in_scope,
        "n_should_refuse": sum(1 for case in cases if case.should_refuse),
        "top_k": top_k,
        "hybrid_prefetch_limit": HYBRID_PREFETCH_LIMIT,
        "reference_threshold": REFERENCE_THRESHOLD,
        "min_true_refusals": args.min_true_refusals,
        "results": results,
    }
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", "utf-8")

    print(
        f"\nDataset {DATASET_V2_PATH.name}: {in_scope} in_scope para retrieval, "
        f"{len(cases)} casos para recusas ({report['n_should_refuse']} a recusar), top_k={top_k}"
    )
    print(format_table(results))
    print(f"\nResultados em {args.output}")


if __name__ == "__main__":
    main()
