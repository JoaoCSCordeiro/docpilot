import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings  # noqa: E402
from src.evaluation.dataset import DATASET_V2_PATH, load_cases  # noqa: E402
from src.evaluation.gate import BASELINE_PATH, find_regressions, load_baseline  # noqa: E402
from src.evaluation.retrieval_eval import (  # noqa: E402
    RETRIEVAL_CATEGORIES,
    evaluate_retrieval,
    gate_metrics,
    summarize_retrieval,
)
from src.retrieval.vector_store import get_client  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


def current_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT
    )
    return result.stdout.strip() or "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieval eval gate (sem LLM)")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Grava as metricas atuais como baseline em vez de comparar.",
    )
    parser.add_argument("--tolerance", type=float, default=None)
    args = parser.parse_args()

    cases = [
        case
        for case in load_cases()
        if case.collection == "main" and case.category in RETRIEVAL_CATEGORIES
    ]
    rows = evaluate_retrieval(
        get_client(), {"main": settings.qdrant_collection_name}, cases, settings.retrieval_top_k
    )
    current = gate_metrics(summarize_retrieval(rows))

    print(
        f"Dataset: {DATASET_V2_PATH.name}, {len(cases)} perguntas in_scope, "
        f"top_k={settings.retrieval_top_k}"
    )
    for name, value in current.items():
        print(f"  {name:<45} {value:.4f}")

    if args.update_baseline:
        baseline = {
            "created_at": dt.date.today().isoformat(),
            "commit": current_commit(),
            "dataset": DATASET_V2_PATH.name,
            "n": len(cases),
            "top_k": settings.retrieval_top_k,
            "embedding_model": settings.embedding_model_name,
            "reranker_model": settings.reranker_model_name,
            "tolerance": args.tolerance if args.tolerance is not None else 0.03,
            "metrics": {name: round(value, 4) for name, value in current.items()},
        }
        BASELINE_PATH.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
        print(f"\nBaseline gravado em {BASELINE_PATH.relative_to(REPO_ROOT)}")
        return

    baseline = load_baseline()
    if args.tolerance is not None:
        baseline["tolerance"] = args.tolerance
    regressions = find_regressions(current, baseline)
    if regressions:
        print(f"\nGate FALHOU ({len(regressions)} metricas abaixo do baseline):")
        for regression in regressions:
            print(f"  {regression}")
        sys.exit(1)
    print(
        f"\nGate OK (tolerancia {baseline['tolerance']}, baseline do commit {baseline['commit']})"
    )


if __name__ == "__main__":
    main()
